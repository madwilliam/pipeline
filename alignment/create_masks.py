import argparse
import subprocess
from multiprocessing.pool import Pool
import numpy as np
import matplotlib
import matplotlib.figure
from skimage import io
from os.path import expanduser
from tqdm import tqdm
HOME = expanduser("~")
import os, sys
import cv2
import pandas as pd

sys.path.append(os.path.join(os.getcwd(), '../'))
from utilities.alignment_utility import get_last_2d, place_image
from utilities.file_location import FileLocationManager

def workershell(cmd):
    """
    Set up an shell command. That is what the shell true is for.
    Args:
        cmd:  a command line program with arguments in a string
    Returns: nothing
    """
    p = subprocess.Popen(cmd, shell=True, stderr=None, stdout=None)
    p.wait()


def find_main_blob(stats, image):
    height, width = image.shape
    df = pd.DataFrame(stats)
    df.columns = ['Left', 'Top', 'Width', 'Height', 'Area']
    df['blob_label'] = df.index
    df = df.sort_values(by='Area', ascending=False)

    for row in df.iterrows():
        Left = row[1]['Left']
        Top = row[1]['Top']
        Width = row[1]['Width']
        Height = row[1]['Height']
        corners = int(Left == 0) + int(Top == 0) + int(Width == width) + int(Height == height)
        if corners <= 2:
            return row


def scale_and_mask(src, mask, epsilon=0.01):
    vals = np.array(sorted(src[mask > 10]))
    ind = int(len(vals) * (1 - epsilon))
    _max = vals[ind]
    # print('thr=%d, index=%d'%(vals[ind],index))
    _range = 2 ** 16 - 1
    scaled = src * (45000. / _max)
    scaled[scaled > _range] = _range
    scaled = scaled * (mask > 10)
    return scaled, _max

def find_threshold(src):
    fig = matplotlib.figure.Figure()
    ax = matplotlib.axes.Axes(fig, (0, 0, 0, 0))
    n, bins, patches = ax.hist(src.flatten(), 360);
    del ax, fig
    min_point = np.argmin(n[:5])
    min_point = int(min(2, min_point))
    thresh = (min_point * 64000 / 360) + 100
    return min_point, thresh

strip_max=70; strip_min=5   # the range of width for the stripe
def remove_strip(src):
    projection=np.sum(src,axis=0)/10000.
    diff=projection[1:]-projection[:-1]
    loc,=np.nonzero(diff[-strip_max:-strip_min]>50)
    mval=np.max(diff[-strip_max:-strip_min])
    no_strip=np.copy(src)
    fe = 0
    if loc.shape[0]>0:
        loc=np.min(loc)
        from_end=strip_max-loc
        fe = -from_end - 2
        no_strip[:,fe:]=0 # mask the strip
    return no_strip, fe

def create_mask(animal, resolution):

    file_location_manager = FileLocationManager(animal)
    INPUT = os.path.join(file_location_manager.prep, 'CH1', 'thumbnail')
    MASKED = os.path.join(file_location_manager.prep, 'thumbnail_masked')

    if 'full' in resolution.lower():
        INPUT = os.path.join(file_location_manager.prep, 'CH1', 'full')
        THUMBNAIL = os.path.join(file_location_manager.prep, 'thumbnail_masked')
        MASKED = os.path.join(file_location_manager.prep, 'full_masked')
        files = sorted(os.listdir(INPUT))
        commands = []
        for i, file in enumerate(tqdm(files)):
            infile = os.path.join(INPUT, file)
            thumbfile = os.path.join(THUMBNAIL, file)
            outfile = os.path.join(MASKED, file)
            try:
                src = io.imread(infile)
            except:
                print('Could not open', infile)
                continue
            height, width = src.shape
            del src
            cmd = "convert {} -resize {}x{}! -compress lzw -depth 8 {}".format(thumbfile, width, height, outfile)
            commands.append(cmd)

        with Pool(4) as p:
            p.map(workershell, commands)

    else:

        files = sorted(os.listdir(INPUT))


        for i, file in enumerate(tqdm(files)):
            infile = os.path.join(INPUT, file)
            try:
                img = io.imread(infile)
            except:
                print('Could not open', infile)
                continue
            img = get_last_2d(img)
            no_strip, fe = remove_strip(img)

            min_value, threshold = find_threshold(img)
            ###### Threshold it so it becomes binary
            # threshold = 272
            ret, threshed = cv2.threshold(no_strip, threshold, 255, cv2.THRESH_BINARY)
            threshed = np.uint8(threshed)
            ###### Find connected elements
            # You need to choose 4 or 8 for connectivity type
            connectivity = 4
            output = cv2.connectedComponentsWithStats(threshed, connectivity, cv2.CV_32S)
            # Get the results
            # The first cell is the number of labels
            num_labels = output[0]
            # The second cell is the label matrix
            labels = output[1]
            # The third cell is the stat matrix
            stats = output[2]
            # The fourth cell is the centroid matrix
            centroids = output[3]
            # Find the blob that corresponds to the section.
            row = find_main_blob(stats, img)
            blob_label = row[1]['blob_label']
            # extract the blob
            blob = np.uint8(labels == blob_label) * 255
            # Perform morphological closing
            kernel10 = np.ones((10, 10), np.uint8)
            closing = cv2.morphologyEx(blob, cv2.MORPH_CLOSE, kernel10, iterations=5)
            del blob
            if fe != 0:
                img[:,fe:]=0 # mask the strip
            # scale and mask
            scaled, _max = scale_and_mask(img, closing)
            # save the mask
            outpath = os.path.join(MASKED, file)
            cv2.imwrite(outpath, closing.astype('uint8'))

            # save the good scaled as CH1
            #outpath = os.path.join(OUTPUT, file)
            #cv2.imwrite(outpath, scaled.astype('uint16'))

if __name__ == '__main__':
    # Parsing argument
    parser = argparse.ArgumentParser(description='Work on Animal')
    parser.add_argument('--animal', help='Enter the animal', required=True)
    parser.add_argument('--resolution', help='full or thumbnail', required=False, default='thumbnail')
    args = parser.parse_args()
    animal = args.animal
    resolution = args.resolution
    create_mask(animal, resolution)

