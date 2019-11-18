import argparse
from clip_word import clip_word
from subprocess import check_output
from speech_to_text import sample_recognize
from youtube_utils import video_to_flac


clean_word = lambda x: ''.join([c for c in x.lower() if c.isalpha() or c.isdigit() or c==' ']).rstrip()

# TODO: Add time checking... Check time for word utterance and cut audio after word.. or dim volume

# TODO: Create videogram. Then Quality check that. If certain word not seen swap out for another edition
#       requires "stocking" of trusted vocab with multiple editions of word
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

#    check_transcription(output_filename, phrase_text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phrase', nargs='+')
    args = parser.parse_args()

    ransom_videogram(args.phrase)
