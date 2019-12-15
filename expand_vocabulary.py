import argparse
from youtube_utils import download_captions
from utils import timecode_to_seconds
import os
import csv


VOCAB_DIRECTORY = './vocabulary'


def expand_vocabulary(video_code):
    # This is where captions will always be downloaded (semi-hardcoded by youtube_dl)
    filepath = f'captions/{video_code}.en.vtt'

    if os.path.exists(filepath):
        print('These captions are already in our vocabulary.')
        return

    download_captions(video_code)
    atomize_captions(video_code, filepath)
    print('Complete!')


def write_to_tsv(row, header, filepath):
    mode = 'w'
    if os.path.exists(filepath):
        mode = 'a'

    with open(filepath, mode) as f:
        writer = csv.writer(f, delimiter='\t', lineterminator='\n')
        if mode == 'w':
            writer.writerow(header)
        writer.writerow(row)



remove_c_tags = lambda x: x.replace('<c>', '').replace('</c>', '')


def atomize_captions(video_code, caption_filepath):
    '''Finds start and end time of all words in .vtt caption file and writes to vocabulary.'''

    master_cue_list = []

    with open(caption_filepath) as f:
        saw_line_timing = False
        line_start = None
        line_end = None

        for line in f.readlines():
            if '-->' in line:
                if saw_line_timing:
                    master_cue_list += [line_start, line_end]

                saw_line_timing = True
                start = f'<{line.split()[0]}>'
                end = f'<{line.split()[2]}>'
                master_cue_list += [start]
                line_start = start
                line_end = end

            if '<c>' in line:
                saw_line_timing = False
                cue_line_list = remove_c_tags(line).replace('<', ' <').split()
                master_cue_list += cue_line_list
                master_cue_list += [line_end]


    for i, entry in enumerate(master_cue_list):
        if '<' in entry:
            seconds = timecode_to_seconds(entry)
            master_cue_list[i] = seconds


    for i, entry in enumerate(master_cue_list):
        if type(entry) == str:
            word = entry
            start_time = master_cue_list[i-1]
            end_time = master_cue_list[i+1]

            vocab_subdirectory = word[0].upper()
            safe_word = ''.join([c for c in word.lower() if c.isalpha() or c.isdigit() or c==' ']).rstrip()

            filename = f'{safe_word}.tsv'
            dir_path = f'{VOCAB_DIRECTORY}/{vocab_subdirectory}'

            if not os.path.exists(dir_path):
                os.makedirs(dir_path)

            write_to_tsv([video_code, start_time, end_time], ['video_code', 'start_time', 'end_time'], f'{dir_path}/{filename}')



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('video_code')
    args = parser.parse_args()
    expand_vocabulary(str(args.video_code))
