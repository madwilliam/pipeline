import os, sys, time
from subprocess import Popen, run, check_output
from multiprocessing.pool import Pool
from tqdm import tqdm
import socket
from pathlib import Path
PIPELINE_ROOT = Path('.').absolute().parent
sys.path.append(PIPELINE_ROOT.as_posix())

from lib.file_location import FileLocationManager
from lib.sqlcontroller import SqlController
from sql_setup import QC_IS_DONE_ON_SLIDES_IN_WEB_ADMIN, CZI_FILES_ARE_CONVERTED_INTO_NUMBERED_TIFS_FOR_CHANNEL_1
from lib.logger import get_logger
SCALING_FACTOR = 0.03125


def get_hostname():
    hostname = socket.gethostname()
    hostname = hostname.split(".")[0]
    return hostname

def get_cpus():
    nmax = 4
    usecpus = (nmax,nmax)
    cpus = {}
    cpus['muralis'] = (16,40)
    cpus['basalis'] = (10,12)
    cpus['ratto'] = (10,10)
    hostname = get_hostname()
    if hostname in cpus.keys():
        usecpus = cpus[hostname]
    return usecpus

def get_image_size(filepath):
    result_parts = str(check_output(["identify", filepath]))
    results = result_parts.split()
    width, height = results[2].split('x')
    return width, height


def workershell(cmd):
    """
    Set up an shell command. That is what the shell true is for.
    Args:
        cmd:  a command line program with arguments in a list
    Returns: nothing
    """
    stderr_template = os.path.join(os.getcwd(), 'workershell.err.log')
    stdout_template = os.path.join(os.getcwd(), 'workershell.log')
    stdout_f = open(stdout_template, "w")
    stderr_f = open(stderr_template, "w")
    proc = Popen(cmd, shell=True, stderr=stderr_f, stdout=stdout_f)
    proc.wait()

def workernoshell(cmd):
    """
    Set up an shell command. That is what the shell true is for.
    Args:
        cmd:  a command line program with arguments in a list
    Returns: nothing
    """
    stderr_template = os.path.join(os.getcwd(), 'workernoshell.err.log')
    stdout_template = os.path.join(os.getcwd(), 'workernoshell.log')
    stdout_f = open(stdout_template, "w")
    stderr_f = open(stderr_template, "w")
    proc = Popen(cmd, shell=False, stderr=stderr_f, stdout=stdout_f)
    proc.wait()


def test_dir(animal, dir, downsample=True, same_size=False):
    error = ""
    #thumbnail resolution ntb is 10400 and min size of DK52 is 16074
    #thumbnail resolution thion is 14464 and min size for MD585 is 21954
    # so 3000 is a good min size
    # min size on NTB is 8.8K
    starting_size = 3000
    min_size = starting_size * SCALING_FACTOR * 1000
    if downsample:
        min_size = starting_size
    
    sqlController = SqlController(animal)
    section_count = sqlController.get_section_count(animal)
    try:
        files = sorted(os.listdir(dir))
    except:
        return f'{dir} does not exist'
        
    if section_count == 0:
        section_count = len(files)
    widths = set()
    heights = set()
    for f in files:
        filepath = os.path.join(dir, f)
        width, height = get_image_size(filepath)
        widths.add(int(width))
        heights.add(int(height))
        size = os.path.getsize(filepath)
        if size < min_size:
            error += f"{size} is less than min: {min_size} {filepath} \n"
    # picked 100 as an arbitrary number. the min file count is usually around 380 or so
    if len(files) > 100:
        min_width = min(widths)
        max_width = max(widths)
        min_height = min(heights)
        max_height = max(heights)
    else:
        min_width = 0
        max_width = 0
        min_height = 0
        max_height = 0
    if section_count != len(files):
        error += f"Number of files in {dir} is incorrect.\n"
    if min_width != max_width and min_width > 0 and same_size:
       error += f"Widths are not of equal size, min is {min_width} and max is {max_width}.\n"
    if min_height != max_height and min_height > 0 and same_size:
        error += f"Heights are not of equal size, min is {min_height} and max is {max_height}.\n"
    return error



def get_last_2d(data):
    if data.ndim <= 2:
        return data
    m,n = data.shape[-2:]
    return data.flat[:m*n].reshape(m,n)



def make_tifs(animal, channel, njobs):
    """
    This method will:
        1. Fetch the sections from the database
        2. Yank the tif out of the czi file according to the index and channel with the bioformats tool.
        3. Then updates the database with updated meta information
    Args:
        animal: the prep id of the animal
        channel: the channel of the stack to process
        njobs: number of jobs for parallel computing
        compression: default is no compression so we can create jp2 files for CSHL. The files get
        compressed using LZW when running create_preps.py

    Returns:
        nothing
    """

    logger = get_logger(animal)
    fileLocationManager = FileLocationManager(animal)
    sqlController = SqlController(animal)
    INPUT = fileLocationManager.czi
    OUTPUT = fileLocationManager.tif
    os.makedirs(OUTPUT, exist_ok=True)
    sections = sqlController.get_distinct_section_filenames(animal, channel)
    sqlController.set_task(animal, QC_IS_DONE_ON_SLIDES_IN_WEB_ADMIN)
    sqlController.set_task(animal, CZI_FILES_ARE_CONVERTED_INTO_NUMBERED_TIFS_FOR_CHANNEL_1)

    commands = []
    for section in sections:
        input_path = os.path.join(INPUT, section.czi_file)
        output_path = os.path.join(OUTPUT, section.file_name)
        cmd = ['/usr/local/share/bftools/bfconvert', '-bigtiff', '-separate', '-series', str(section.scene_index),
                '-channel', str(section.channel_index),  '-nooverwrite', input_path, output_path]

        if not os.path.exists(input_path):
            continue

        if os.path.exists(output_path):
            continue

        commands.append(cmd)

    with Pool(njobs) as p:
        p.map(workernoshell, commands)


def make_scenes(animal):
    fileLocationManager = FileLocationManager(animal)
    INPUT = fileLocationManager.tif
    OUTPUT = os.path.join(fileLocationManager.thumbnail_web, 'scene')
    os.makedirs(OUTPUT, exist_ok=True)

    convert_commands = []
    tifs = os.listdir(INPUT)
    for tif in tifs:
        tif_path = os.path.join(INPUT, tif)
        if not tif.endswith('_C1.tif'):
            continue

        png = tif.replace('tif', 'png')
        png_path = os.path.join(OUTPUT, png)
        if os.path.exists(png_path):
            continue

        # convert tif to png
        cmd = ['convert', tif_path, '-resize', '3.125%', '-normalize', png_path]
        convert_commands.append(cmd)


    with Pool(4) as p:
        p.map(workernoshell, convert_commands)


def make_tif(animal, tif_id, file_id, testing=False):
    fileLocationManager = FileLocationManager(animal)
    sqlController = SqlController(animal)
    INPUT = fileLocationManager.czi
    OUTPUT = fileLocationManager.tif
    start = time.time()
    tif = sqlController.get_tif(tif_id)
    slide = sqlController.get_slide(tif.slide_id)
    czi_file = os.path.join(INPUT, slide.file_name)
    section = sqlController.get_section(file_id)
    tif_file = os.path.join(OUTPUT, section.file_name)
    if not os.path.exists(czi_file) and not testing:
        return 0
    if os.path.exists(tif_file):
        return 1

    if testing:
        command = ['touch', tif_file]
    else:
        command = ['/usr/local/share/bftools/bfconvert', '-bigtiff', '-separate',
                                  '-series', str(tif.scene_index), '-channel', str(tif.channel-1), '-nooverwrite', czi_file, tif_file]
    run(command)

    end = time.time()
    if os.path.exists(tif_file):
        tif.file_size = os.path.getsize(tif_file)

    tif.processing_duration = end - start
    sqlController.update_row(tif)

    return 1

