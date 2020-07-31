import cv2
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.figure

from utilities.alignment_utility import get_last_2d


def rotate_image(img, file, rotation):
    try:
        img = np.rot90(img, rotation)
    except:
        print('Could not rotate', file)
    return img

def linnorm(img, limit, dt):
    flat = img.flatten()
    hist, bins = np.histogram(flat, limit + 1)
    cdf = hist.cumsum()  # cumulative distribution function
    cdf = limit * cdf / cdf[-1]  # normalize
    # use linear interpolation of cdf to find new pixel values
    img_norm = np.interp(flat, bins[:-1], cdf)
    img_norm = np.reshape(img_norm, img.shape)
    return img_norm.astype(dt)

def find_contour_count(img):
    contours, hierarchy = cv2.findContours(img.astype(np.uint8), cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    return len(contours)

def fix_with_blob(img):
    no_strip, fe = remove_strip(img)
    min_value, threshold = find_threshold(img)
    ret, threshed = cv2.threshold(no_strip, threshold, 255, cv2.THRESH_BINARY)
    threshed = np.uint8(threshed)
    connectivity = 4
    output = cv2.connectedComponentsWithStats(threshed, connectivity, cv2.CV_32S)
    labels = output[1]
    stats = output[2]
    # Find the blob that corresponds to the section.
    if fe != 0:
        img[:, fe:] = 0  # mask the strip
    row = find_main_blob(stats, img)
    blob_label = row[1]['blob_label']
    # extract the blob
    blob = np.uint8(labels == blob_label) * 255
    # Perform morphological closing
    kernel10 = np.ones((10, 10), np.uint8)
    mask = cv2.morphologyEx(blob, cv2.MORPH_CLOSE, kernel10, iterations=5)
    return mask


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
    thresh = (min_point * 64000 / 360)
    return min_point, thresh

def remove_strip(src):
    strip_max = 150;
    strip_min = 5  # the range of width for the stripe
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


def make_mask(img):
    img = get_last_2d(img)
    no_strip, fe = remove_strip(img)

    # Threshold it so it becomes binary
    min_value, threshold = find_threshold(img)
    # threshold = 272
    ret, threshed = cv2.threshold(no_strip, threshold, 255, cv2.THRESH_BINARY)
    threshed = np.uint8(threshed)

    # Find connected elements
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
        img[:, fe:] = 0  # mask the strip
    # scale and mask
    scaled, _max = scale_and_mask(img, closing)

    return closing, scaled


def place_image(img, file, max_width, max_height, bgcolor=None):
    zmidr = max_height // 2
    zmidc = max_width // 2
    startr = zmidr - (img.shape[0] // 2)
    endr = startr + img.shape[0]
    startc = zmidc - (img.shape[1] // 2)
    endc = startc + img.shape[1]
    dt = img.dtype
    if bgcolor == None:
        start_bottom = img.shape[0] - 5
        bottom_rows = img[start_bottom:img.shape[0], :]
        avg = np.mean(bottom_rows)
        bgcolor = int(round(avg))
    new_img = np.zeros([max_height, max_width]) + bgcolor
    if img.ndim == 2:
        try:
            new_img[startr:endr, startc:endc] = img
        except:
            print('Could not place {} with width:{}, height:{} in {}x{}'
                  .format(file, img.shape[1], img.shape[0], max_width, max_height))
    if img.ndim == 3:
        try:
            new_img = np.zeros([max_height, max_width, 3]) + bgcolor
            new_img[startr:endr, startc:endc,0] = img[:,:,0]
            new_img[startr:endr, startc:endc,1] = img[:,:,1]
            new_img[startr:endr, startc:endc,2] = img[:,:,2]
        except:
            print('Could not place {} with width:{}, height:{} in {}x{}'
                  .format(file, img.shape[1], img.shape[0], max_width, max_height))

    return new_img.astype(dt)


def pad_with_black(img):
    r,c = img.shape
    pad = 12
    img[0:pad,:] = 0 # top
    img[:,c-5:c] = 0 # right
    img[r-pad:r,:] = 0 # bottom
    img[:,0:5] = 0 # left
    return img


def get_index(array, list_of_arrays):
    for j, a in enumerate(list_of_arrays):
        if np.array_equal(array, a):
            return j
    return None

def fill_spots(img):
    imgcopy = np.copy(img)
    #imgcopy = (imgcopy / 256).astype(np.uint8)

    contours, hierarchy = cv2.findContours(imgcopy, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

    if len(contours) == 0:
        return img

    c1 = max(contours, key=cv2.contourArea)
    area1 = cv2.contourArea(c1)
    idx = get_index(c1, contours)  # 2
    contours.pop(idx)

    if len(contours) > 0:
        cX = max(contours, key=cv2.contourArea)
        area2 = cv2.contourArea(cX)
        if area2 > (area1 * 0.75):
            idx = get_index(cX, contours)  # 2
            contours.pop(idx)

    if len(contours) > 0:
        cX = max(contours, key=cv2.contourArea)
        area3 = cv2.contourArea(cX)
        if area3 > (area2 * 0.75):
            idx = get_index(cX, contours)  # 2
            contours.pop(idx)

    """
    if len(contours) > 0:
        cX = max(contours, key=cv2.contourArea)
        area3 = cv2.contourArea(cX)
        if area3 > (area1 * 0.95):
            idx = get_index(cX, contours)  # 2
            contours.pop(idx)

    if len(contours) > 0:
        cX = max(contours, key=cv2.contourArea)
        area4 = cv2.contourArea(cX)
        if area4 > (area3 * 0.95):
            idx = get_index(cX, contours)  # 2
            contours.pop(idx)
    """

    if len(contours) > 0:
        cv2.fillPoly(img, contours, 0)

    return img

def check_contour(contours, area, lc):
    if len(contours) > 0:
        cX = max(contours, key=cv2.contourArea)
        areaX = cv2.contourArea(cX)
        if areaX > (area * 0.05):
            lc.append(cX)
            idx = get_index(cX, contours)
            contours.pop(idx)
        return contours, lc


def fix_with_fill(img, limit, dt):
    no_strip, fe = remove_strip(img)
    if fe != 0:
        img[:, fe:] = 255  # mask the strip
    img = pad_with_black(img)
    img = (img / 256).astype(dt)
    h_src = linnorm(img, limit, dt)
    med = np.median(h_src) + 10
    h, im_th = cv2.threshold(h_src, med, limit, cv2.THRESH_BINARY)
    im_floodfill = im_th.copy()
    h, w = im_th.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(im_floodfill, mask, (0, 0), 255)
    im_floodfill_inv = cv2.bitwise_not(im_floodfill)
    im_out = im_th | im_floodfill_inv
    stencil = np.zeros(img.shape).astype('uint8')

    # dilation = cv2.dilate(stencil,kernel,iterations = 2)
    small_kernel = np.ones((6, 6), np.uint8)
    big_kernel = np.ones((16, 16), np.uint8)
    eroded = cv2.erode(im_out, small_kernel, iterations=1)
    #eroded = np.copy(im_out)
    contours, hierarchy = cv2.findContours(eroded, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    lc = []
    midcolumn = img.shape[1] // 2
    leftbound = midcolumn - (midcolumn * 0.5)
    rightbound = midcolumn + (midcolumn * 0.5)
    AREA_THRESHOLD = 0.05
    if len(contours) > 0:
        c1 = max(contours, key=cv2.contourArea)
        lc.append(c1)
        area1 = cv2.contourArea(c1)
        idx = get_index(c1, contours)
        contours.pop(idx)

        if len(contours) > 0:
            cX = max(contours, key=cv2.contourArea)
            area2 = cv2.contourArea(cX)
            mX = cv2.moments(cX)
            m00 = mX['m00']
            if m00 > 0:
                cx = mX['m10'] // m00
                if (area2 > (area1 * AREA_THRESHOLD) and cx > leftbound and cx < rightbound):
                    lc.append(cX)
                    idx = get_index(cX, contours)
                    contours.pop(idx)

        if len(contours) > 0:
            cX = max(contours, key=cv2.contourArea)
            area3 = cv2.contourArea(cX)
            mX = cv2.moments(cX)
            m00 = mX['m00']
            if m00 > 0:
                cx = mX['m10'] // m00
                if (area3 > (area2 * AREA_THRESHOLD) and cx > leftbound and cx < rightbound):
                    lc.append(cX)
                    idx = get_index(cX, contours)
                    contours.pop(idx)

        if len(contours) > 0:
            cX = max(contours, key=cv2.contourArea)
            area4 = cv2.contourArea(cX)
            mX = cv2.moments(cX)
            m00 = mX['m00']
            if m00 > 0:
                cx = mX['m10'] // m00
                if (area4 > (area3 * AREA_THRESHOLD) and cx > leftbound and cx < rightbound):
                    lc.append(cX)
                    idx = get_index(cX, contours)
                    contours.pop(idx)

        cv2.fillPoly(stencil, lc, 255)

        if len(contours) > 0:
            cv2.fillPoly(stencil, contours, 0)
    #erosion = cv2.erode(stencil, small_kernel, iterations=1)
    dilation = cv2.dilate(stencil, big_kernel, iterations=5)
    mask = fill_spots(dilation)

    return mask


def fix_thionin(img):

    start_bottom = img.shape[0] - 5
    bottom_rows = img[start_bottom:img.shape[0], :]
    avg = np.mean(bottom_rows)
    bgcolor = int(round(avg))
    lower = bgcolor - 8
    upper = bgcolor + 4
    bgmask = (img >= lower) & (img <= upper)
    img[bgmask] = bgcolor

    clahe = cv2.createCLAHE(clipLimit=40.0, tileGridSize=(16, 16))
    h_src = clahe.apply(img)
    start_bottom = h_src.shape[0] - 5
    bottom_rows = h_src[start_bottom:h_src.shape[0], :]
    avg = np.mean(bottom_rows)
    # -10 too much
    # -70 pretty good
    # -90 missing stuff
    bgcolor = int(round(avg)) - 50

    h, im_th = cv2.threshold(h_src, bgcolor, 255, cv2.THRESH_BINARY_INV)
    im_floodfill = im_th.copy()
    h, w = im_th.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(im_floodfill, mask, (0, 0), 255)
    im_floodfill_inv = cv2.bitwise_not(im_floodfill)
    im_out = im_th | im_floodfill_inv

    stencil = np.zeros(img.shape).astype('uint8')
    contours, hierarchy = cv2.findContours(im_out, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

    lc = []
    c1 = max(contours, key=cv2.contourArea)
    area0 = cv2.contourArea(c1)
    lc.append(c1)
    idx = get_index(c1, contours)
    contours.pop(idx)

    midrow = img.shape[0] // 2
    topbound = midrow - (midrow * 0.75)
    bottombound = midrow + (midrow * 0.5)
    midcolumn = img.shape[1] // 2
    leftbound = midcolumn - (midcolumn * 0.75)
    rightbound = midcolumn + (midcolumn * 0.95)
    #rightbound = img.shape[1]
    AREA_THRESHOLD = 0.05
    if len(contours) > 0:

        if len(contours) > 0:
            cX = max(contours, key=cv2.contourArea)
            area1 = cv2.contourArea(cX)
            mX = cv2.moments(cX)
            m00 = mX['m00']
            if m00 > 0:
                cx = mX['m10'] // m00
                cy = mX['m01'] // m00
                if (area1 > (area0 * AREA_THRESHOLD)
                        and cx > leftbound and cx < rightbound) and cy > topbound and cy < bottombound:
                    lc.append(cX)
                    idx = get_index(cX, contours)
                    contours.pop(idx)

        if len(contours) > 0:
            cX = max(contours, key=cv2.contourArea)
            area2 = cv2.contourArea(cX)
            mX = cv2.moments(cX)
            m00 = mX['m00']
            if m00 > 0:
                cx = mX['m10'] // m00
                cy = mX['m01'] // m00
                if (area2 > (area1 * AREA_THRESHOLD)
                        and cx > leftbound and cx < rightbound) and cy > topbound and cy < bottombound:
                    lc.append(cX)
                    idx = get_index(cX, contours)
                    contours.pop(idx)

        if len(contours) > 0:
            cX = max(contours, key=cv2.contourArea)
            area3 = cv2.contourArea(cX)
            mX = cv2.moments(cX)
            m00 = mX['m00']
            if m00 > 0:
                cx = mX['m10'] // m00
                cy = mX['m01'] // m00
                if (area3 > (area2 * AREA_THRESHOLD)
                        and cx > leftbound and cx < rightbound) and cy > topbound and cy < bottombound:
                    lc.append(cX)
                    idx = get_index(cX, contours)
                    contours.pop(idx)

        if len(contours) > 0:
            cX = max(contours, key=cv2.contourArea)
            area4 = cv2.contourArea(cX)
            mX = cv2.moments(cX)
            m00 = mX['m00']
            if m00 > 0:
                cx = mX['m10'] // m00
                cy = mX['m01'] // m00
                if (area4 > (area3 * AREA_THRESHOLD)
                        and cx > leftbound and cx < rightbound) and cy > topbound and cy < bottombound:
                    lc.append(cX)
                    idx = get_index(cX, contours)
                    contours.pop(idx)

        cv2.fillPoly(stencil, lc, 255)

    # dilation1 = cv2.erode(opening, big_kernel, iterations=1)
    big_kernel = np.ones((16, 16), np.uint8)
    dilation = cv2.dilate(stencil, big_kernel, iterations=3)

    return dilation


def fix_thioninXXX(src):
    big_kernel = np.ones((8, 8), np.uint8)
    start_bottom = src.shape[0] - 5
    bottom_rows = src[start_bottom:src.shape[0], :]
    avg = np.mean(bottom_rows)
    bgcolor = int(round(avg))
    lower = bgcolor - 8
    upper = bgcolor + 4
    bgmask = (src >= lower) & (src <= upper)
    src[bgmask] = bgcolor

    clahe = cv2.createCLAHE(clipLimit=40.0, tileGridSize=(16, 16))
    h_src = clahe.apply(src)
    start_bottom = h_src.shape[0] - 5
    bottom_rows = h_src[start_bottom:h_src.shape[0], :]
    avg = np.mean(bottom_rows)
    bgcolor = int(round(avg)) - 50

    h, im_th = cv2.threshold(h_src, bgcolor, 255, cv2.THRESH_BINARY_INV)
    im_floodfill = im_th.copy()
    h, w = im_th.shape[:2]
    mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(im_floodfill, mask, (0, 0), 255)
    im_floodfill_inv = cv2.bitwise_not(im_floodfill)
    im_out = im_th | im_floodfill_inv

    stencil = np.zeros(src.shape).astype('uint8')
    contours, hierarchy = cv2.findContours(im_out, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)

    lc = []
    c1 = max(contours, key=cv2.contourArea)
    lc.append(c1)
    area1 = cv2.contourArea(c1)

    idx = get_index(c1, contours)  # 2
    contours.pop(idx)
    if len(contours) > 0:
        c2 = max(contours, key=cv2.contourArea)
        area2 = cv2.contourArea(c2)
        if area2 > 610:
            lc.append(c2)
    cv2.fillPoly(stencil, lc, 255)

    if area1 > 3000:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
        opening = cv2.morphologyEx(stencil, cv2.MORPH_OPEN, kernel, iterations=3)
    else:
        opening = stencil

    # dilation1 = cv2.erode(opening, big_kernel, iterations=1)
    dilation2 = cv2.dilate(opening, big_kernel, iterations=3)
    dilation3 = fill_spots(dilation2)

    return dilation3
