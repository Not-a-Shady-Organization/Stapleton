from subprocess import check_output
import youtube_dl
from google.cloud import storage



def upload_blob(bucket_name, source_file_name, destination_blob_name):
    """Uploads a file to the bucket."""
    storage_client = storage.Client()
    bucket = storage_client.get_bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)

    blob.upload_from_filename(source_file_name)

    print('File {} uploaded to {}.'.format(
            source_file_name,
            destination_blob_name
        )
    )


def video_to_flac(video_filepath, mono_filepath, log_filepath=''):
    with open(log_filepath, 'a') as log:
        log.write(f'Converting {video_filepath} to audio...\n')

        flac_to_mono_flac_command = f'ffmpeg -y -i {video_filepath} -c:a flac -ac 1 {mono_filepath}'
        log.write(f'Executing: {flac_to_mono_flac_command}\n')
        check_output(flac_to_mono_flac_command, shell=True, stderr=log)


def seconds_to_timecode(seconds):
    remainder = seconds
    h = int(remainder) // 3600
    remainder = remainder - (h*3600)
    m = int(remainder) // 60
    remainder = remainder - (m*60)
    s = remainder % 60
    return f'{h}:{m}:{s}'


def timecode_to_seconds(timecode):
    h, m, seconds = timecode[1:-1].split(':')
    s, ms = seconds.split('.')
    return int(h)*60*60 + int(m)*60 + int(s) + float(ms)/1000


def download_captions(video_code):
    video_url = 'https://www.youtube.com/watch?v=' + video_code

    # Define the Youtube extractor to only grab english subtitles
    ydl = youtube_dl.YoutubeDL({
        'outtmpl': 'captions/' + video_code,
        'skip_download': True,
        'noplaylist': True,
        'subtitleslangs': ['en'],
        'subtitlesformat': 'vtt',
        'writesubtitles': True,
        'writeautomaticsub': True
    })

    # Download
    with ydl:
        result = ydl.extract_info(video_url)


def change_video_speed(video_filepath, multiplier, output_filepath, log_filepath=''):
    command = f'ffmpeg -y -i {video_filepath} -filter_complex "[0:v]setpts={str(float(1/multiplier))}*PTS[v];[0:a]atempo={str(multiplier)}[a]" -map "[v]" -map "[a]" {output_filepath}'
    with open(log_filepath, 'a') as log:
        log.write(f'Executing: {command}\n')
        check_output(command, shell=True, stderr=log)


def video_code_to_url(video_code, log_filepath=''):
    url = f'https://www.youtube.com/watch?v={video_code}'
    command = f'youtube-dl -g {url}'
    with open(log_filepath, 'a') as log:
        response = check_output(command, shell=True, stderr=log).decode().split('\n')[:-1]
    return response

# TODO: If you start to close to the beginning of a video, we fail for lookahead
def download_video(video_code, start_time, end_time, output, safety_buffer=5, lookahead=10, log_filepath=''):
    clip_length = end_time - start_time + (2 * safety_buffer)

    # Get the true URLs of audio and video from the video_code
    url_one, url_two = video_code_to_url(video_code, log_filepath)

    ffmpeg_command = f'ffmpeg -y -ss {seconds_to_timecode(start_time - lookahead)} -i "{url_one}" -ss {seconds_to_timecode(start_time - lookahead)} -i "{url_two}" -map 0:v -map 1:a -ss {lookahead - safety_buffer} -t {seconds_to_timecode(clip_length)} -c:v libx264 -c:a aac {output}'
    with open(log_filepath, 'a') as log:
        check_output(ffmpeg_command, shell=True, stderr=log)
