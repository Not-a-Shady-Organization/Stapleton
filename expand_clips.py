import argparse
from clip_word import clip_word
from subprocess import check_output
from speech_to_text import sample_recognize
from youtube_utils import video_to_flac


clean_word = lambda x: ''.join([c for c in x.lower() if c.isalpha() or c.isdigit() or c==' ']).rstrip()

# TODO: Add time checking... Check time for word utterance and cut audio after word.. or dim volume

def expand_clips(letter):
    words = [x.replace('.tsv', '') for x in check_output(f'ls vocabulary/{letter}', shell=True).decode().split()]

    for word in words:
        # Download a clip for this word
        try:
            filepath = clip_word(word)
        except FileNotFoundError:
            continue



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('letter')
    args = parser.parse_args()

    expand_clips(args.letter)
