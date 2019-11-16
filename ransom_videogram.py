import argparse
from clip_word import clip_word
from subprocess import check_output
from speech_to_text import sample_long_running_recognize
from youtube_utils import upload_blob, video_to_flac


clean_word = lambda x: ''.join([c for c in x.lower() if c.isalpha() or c.isdigit() or c==' ']).rstrip()

def check_transcription(filename, phrase):
    audio_filepath = video_to_flac(phrase, 'videograms/' + filename)
    upload_blob('motley-audio-clips', audio_filepath, f'{filename}')
#    text = sample_long_running_recognize(f'gs://motley-audio-clips/{filename}')

#    transcript = text.transcript
#    if transcript == text.transcript:
#        print('Videogram matches phrase!')

    pass


def ransom_videogram(phrase):
    safe_phrase = [clean_word(word) for word in phrase]

    # Create a file defining which videos to concat
    with open('concat.txt', 'w') as f:
        for word in safe_phrase:
            # Download a clip for this word
            filepath = clip_word(word)

            f.write(f"file '{filepath}'\n")

    # Feed the file to ffmpeg
    phrase_text = "-".join(safe_phrase)
    output_filename = f'{phrase_text}.mkv'
    stitch_command = f'ffmpeg -f concat -safe 0 -i concat.txt -c copy videograms/{output_filename}'
    check_output(stitch_command, shell=True)

    check_transcription(output_filename, phrase_text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phrase', nargs='+')
    args = parser.parse_args()

    ransom_videogram(args.phrase)
