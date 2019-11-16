import argparse
import os
import csv
from subprocess import check_output
from youtube_utils import download_video, video_to_flac, upload_blob, change_video_speed
from speech_to_text import sample_recognize


VOCAB_DIRECTORY = './vocabulary'

clean_word = lambda x: ''.join([c for c in x.lower() if c.isalpha() or c.isdigit() or c==' ']).rstrip()

def get_word_time(word, audio_filepath, min_confidence=0.7):
    # TODO: Allow for close matches e.g. Hillbillies to hill billies
    # Use GCP Speech-to-Text to refine clip cropping
    found_word = False
    start_time = 0
    end_time = 0
    confidence = 0
    text = sample_recognize(audio_filepath)
    for w in text.words:
        # TODO: Fix this.. I believe we're not matching words on the quality check
        if clean_word(w.word) == word:
            found_word = True
            start_time = float(str(w.start_time.seconds) + '.' + str(w.start_time.nanos))
            end_time = float(str(w.end_time.seconds) + '.' + str(w.end_time.nanos))
            confidence = float(w.confidence)

    if not found_word or confidence < min_confidence:
        raise FileNotFoundError("GCP didn't detect the word in our clip. Exiting...")

    return start_time, end_time


def get_clip_information(word):
    tsv_filepath = vocabulary_filepath(word)
    clip_info_list = []
    with open(tsv_filepath, mode='r') as infile:
        reader = csv.reader(infile, delimiter='\t')
        next(reader)
        for row in reader:
            clip_info_list += [(row[0], float(row[1]), float(row[2]))]
    return clip_info_list


def erase_tsv_row(word):
    # Read all into memory
    tsv_filepath = vocabulary_filepath(word)
    clip_info_list = []
    with open(tsv_filepath, mode='r') as infile:
        reader = csv.reader(infile, delimiter='\t')
        next(reader)
        for row in reader:
            clip_info_list += [(row[0], float(row[1]), float(row[2]))]

    clip_info_list = clip_info_list[1:]

    # Delete TSV
    os.remove(tsv_filepath)

    # Quit here if no clips are left
    if clip_info_list == []:
        return

    with open(tsv_filepath, mode='w') as out:
        writer = csv.writer(out, delimiter='\t', lineterminator='\n')
        writer.writerow(['video_code', 'start_time', 'end_time'])
        for row in clip_info_list:
            writer.writerow(row)


def vocabulary_filepath(word):
    vocab_subdirectory = word[0].upper()
    filepath = f'{VOCAB_DIRECTORY}/{vocab_subdirectory}/{word}.tsv'
    return filepath


def clip_word(word):
    '''
    Algorithm
        Clean word (to avoid errors from bad strings & directories)

        (1) Locate clip information
            If word not in caption vocabulary, throw error
            Select row one instance of word from vocabulary/[first letter of word]/[word].tsv
        (2) Download & trim clip
            Download row one clip with spare leading and trailing time (approx 1 second)
            Convert to FLAC
            Use GCP Speech-to-text API to find accurate word start and end time
            Trim downloaded clip to just the word
        (3) Check quality
            Convert new clip to FLAC
            Use GCP to transcribe clip
            If transcription is not just our word, remove row one of TSV & return to (1)
    '''
    # TODO
    # Stop re-downloading elements if they exist locally
    # Also delete videos or move to an archive if they are failures

    # Clean word
    safe_word = clean_word(word)

    # If word not in vocabulary, throw error
    filepath = vocabulary_filepath(safe_word)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"We don't have the word {safe_word} yet!")

    # Get information on all clips of the word
    clip_info_list = get_clip_information(safe_word)

    # TODO: Add selection functions
    # Pick clip to use
    clip_info = clip_info_list[0]

    # Download a clip which includes the word, plus some time on both sides
    video_code, start_time, end_time = clip_info
    output = f'clips/{safe_word}.mkv'
    download_video(video_code, start_time, end_time, output, safety_buffer=1)

    # NOTE: "Apocalyptic" didn't work full speed, but was recognized when slowed!!!!!!
    output = change_video_speed(output, 0.7)

    # Upload the audio to GCP
    audio_filepath = video_to_flac(safe_word, output)
    try:
        start_time, end_time = get_word_time(safe_word, audio_filepath)
    except:
        erase_tsv_row(safe_word)
        print(f"First row of {safe_word} TSV erased")
        exit()

    # TODO: Handle filepaths better. Trimming won't work after speed-change
    # Retrim
    cropping_command = f'ffmpeg -ss 0 -i clips/{safe_word}.mkv -ss {start_time} -t {end_time - start_time} -c:v libx264 -c:a aac word-clips/{safe_word}.mkv'
    print('Executing: ', cropping_command)
    check_output(cropping_command, shell=True)

    # Check quality of trimmed clip
    audio_filepath = video_to_flac(safe_word, f'word-clips/{safe_word}.mkv')
    try:
        start_time, end_time = get_word_time(safe_word, audio_filepath, min_confidence=0.75)
        print("IMPORTANT TO CHECK:", start_time, end_time)
    except:
        erase_tsv_row(safe_word)
        print(f"First row of {safe_word} TSV erased")
        exit()

    # TODO: IF quality check failed.......

    return f'word-clips/{safe_word}.mkv'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('word')
    args = parser.parse_args()

    clip_word(str(args.word))
