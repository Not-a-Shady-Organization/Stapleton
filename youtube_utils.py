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


def video_to_flac(word, video_filepath):
    convert_to_flac_command = f'ffmpeg -y -i {video_filepath} -c:a flac audio/dual-{word}.flac'
    check_output(convert_to_flac_command, shell=True)

    flac_to_mono_flac_command = f'ffmpeg -y -i audio/dual-{word}.flac -ac 1 audio/mono-{word}.flac'
    check_output(flac_to_mono_flac_command, shell=True)

    return f'audio/mono-{word}.flac'


def audio_to_captions(audio_filepath):
    speech_recognition_command = f'{audio_filepath}'



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


def change_video_speed(video, multiplier):
    command = f'ffmpeg -i {video} -filter_complex "[0:v]setpts={str(float(1/multiplier))}*PTS[v];[0:a]atempo={str(multiplier)}[a]" -map "[v]" -map "[a]" slow-{video}'
    print(f'Executing: {command}')
    check_output(command, shell=True)
    return f'slow-{video}'


def video_code_to_url(video_code):
    url = f'https://www.youtube.com/watch?v={video_code}'
    command = f'youtube-dl -g {url}'
    response = check_output(command, shell=True).decode().split('\n')[:-1]
    return response

# TODO: If you start to close to the beginning of a video, we fail for lookahead
def download_video(video_code, start_time, end_time, output, safety_buffer=5, lookahead=10):
    # lookahead: lead time to grab keyframes from
    # start_reading: time to start downloading OFFSET from the lookahead
    # clip_length: video amount to download after t=(start_time - lookahead + start_reading)
    clip_length = end_time - start_time + (2 * safety_buffer)

    # Get the true URLs of audio and video from the video_code
    url_one, url_two = video_code_to_url(video_code)

    ffmpeg_command = f'ffmpeg -y -ss {seconds_to_timecode(start_time - lookahead)} -i "{url_one}" -ss {seconds_to_timecode(start_time - lookahead)} -i "{url_two}" -map 0:v -map 1:a -ss {lookahead - safety_buffer} -t {seconds_to_timecode(clip_length)} -c:v libx264 -c:a aac {output}'
    check_output(ffmpeg_command, shell=True)
