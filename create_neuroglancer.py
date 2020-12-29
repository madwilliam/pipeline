"""
This takes the image stack that has section to section alignment
and creates the neuroglancer precomputed volume. It works on thumbnails by default and
works by channel
"""
import argparse
import os, sys
import json
from skimage import io
from neuroglancer_scripts.scripts import (generate_scales_info,
                                          slices_to_precomputed,
                                          compute_scales)

from sql_setup import CREATE_NEUROGLANCER_TILES_CHANNEL_1_THUMBNAILS, RUN_PRECOMPUTE_NEUROGLANCER_CHANNEL_1_FULL_RES, \
    RUN_PRECOMPUTE_NEUROGLANCER_CHANNEL_2_FULL_RES, RUN_PRECOMPUTE_NEUROGLANCER_CHANNEL_3_FULL_RES
from utilities.utilities_alignment import SCALING_FACTOR
from utilities.sqlcontroller import SqlController
from utilities.file_location import FileLocationManager
from utilities.utilities_process import test_dir


def convert_to_precomputed(folder_to_convert_from, folder_to_convert_to, resolution):
    """
    Takes the directory with aligned images and creates a new directory available
    to the internet. Uses resolution from database and 20000 as width of section
    in nanometers.
    :param folder_to_convert_from: list of aligned and cleaned images
    :param folder_to_convert_to: neuroglancer folder available to the web
    :param resolution: either full or thumbnail
    :return: nothing
    """

    voxel_resolution = [resolution, resolution, 20000]
    voxel_offset = [0, 0, 0]

    info_fullres_template = {
        "type": "image",
        "num_channels": None,
        "scales": [{
            "chunk_sizes": [],
            "encoding": "raw",
            "key": "full",
            "resolution": [None, None, None],
            "size": [None, None, None],
            "voxel_offset": voxel_offset}],
        "data_type": None}

    # make a folder under the "precomputed" dir and execute conversion routine
    if not os.path.isdir(folder_to_convert_from):
        raise NotADirectoryError
    # make a corresponding folder in the "precomputed_dir"
    if not os.path.exists(folder_to_convert_to):
        os.makedirs(folder_to_convert_to)
    # read 1 image to get the shape
    imgs = os.listdir(folder_to_convert_from)
    img = io.imread(os.path.join(folder_to_convert_from, imgs[0]))
    # write info_fullres.json
    info_fullres = info_fullres_template.copy()
    info_fullres['scales'][0]['size'] = [img.shape[1], img.shape[0], len(imgs)]
    info_fullres['scales'][0]['resolution'] = voxel_resolution
    info_fullres['num_channels'] = img.shape[2] if len(img.shape) > 2 else 1
    info_fullres['data_type'] = str(img.dtype)
    with open(os.path.join(folder_to_convert_to, 'info_fullres.json'), 'w') as outfile:
        json.dump(info_fullres, outfile)

    # --- neuroglancer-scripts routine ---
    #  generate_scales_info - make info.json
    generate_scales_info.main(['', os.path.join(folder_to_convert_to, 'info_fullres.json'),
                               folder_to_convert_to])
    # slices_to_precomputed - build the precomputed for the fullress
    slices_to_precomputed.main(
        ['', folder_to_convert_from, folder_to_convert_to, '--flat', '--no-gzip'])
    # compute_scales - build the precomputed for other scales
    compute_scales.main(['', folder_to_convert_to, '--flat', '--no-gzip'])

def run_neuroglancer(animal, channel, full, suffix=None):
    """
    Main method to setup the precomputed volume creation. We also test if the
    input dir has a correct number of sections and they are of the correct size.
    :param animal: prep_id of animal
    :param channel:  channel {1,2,3}
    :param full: either full or thumbnail
    :param suffix: if we want another directory use this to create a different named directory.
    This is useful if we want additional dirs
    :return: nothing
    """
    fileLocationManager = FileLocationManager(animal)
    sqlController = SqlController(animal)
    channel_dir = 'CH{}'.format(channel)
    channel_outdir = 'C{}T'.format(channel)
    INPUT = os.path.join(fileLocationManager.prep, channel_dir, 'thumbnail_aligned')
    sqlController.set_task(animal, CREATE_NEUROGLANCER_TILES_CHANNEL_1_THUMBNAILS)
    planar_resolution = sqlController.scan_run.resolution
    resolution = int(planar_resolution * 1000 / SCALING_FACTOR)

    if full:
        INPUT = os.path.join(fileLocationManager.prep, channel_dir, 'full_aligned')
        channel_outdir = 'C{}'.format(channel)
        if channel == 3:
            sqlController.set_task(animal, RUN_PRECOMPUTE_NEUROGLANCER_CHANNEL_3_FULL_RES)
        elif channel == 2:
            sqlController.set_task(animal, RUN_PRECOMPUTE_NEUROGLANCER_CHANNEL_2_FULL_RES)
        else:
            sqlController.set_task(animal, RUN_PRECOMPUTE_NEUROGLANCER_CHANNEL_1_FULL_RES)

        if 'thion' in sqlController.histology.counterstain:
            sqlController.set_task(animal, RUN_PRECOMPUTE_NEUROGLANCER_CHANNEL_2_FULL_RES)
            sqlController.set_task(animal, RUN_PRECOMPUTE_NEUROGLANCER_CHANNEL_3_FULL_RES)

        resolution = int(planar_resolution * 1000)

    NEUROGLANCER = os.path.join(fileLocationManager.neuroglancer_data, '{}'.format(channel_outdir))
    if suffix is not None:
        NEUROGLANCER += suffix

    error = test_dir(animal, INPUT, full, same_size=True)
    if len(error) > 0:
        print(error)
        sys.exit()
    else:
        convert_to_precomputed(INPUT, NEUROGLANCER, resolution)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Work on Animal')
    parser.add_argument('--animal', help='Enter the animal animal', required=True)
    parser.add_argument('--channel', help='Enter channel', required=True)
    parser.add_argument('--resolution', help='Enter full or thumbnail', required=False, default='thumbnail')
    parser.add_argument('--suffix', help='Enter suffix to add to the output dir', required=False, default=None)

    args = parser.parse_args()
    animal = args.animal
    channel = args.channel
    full = bool({'full': True, 'thumbnail': False}[args.resolution])
    suffix = args.suffix
    run_neuroglancer(animal, channel, full, suffix)
