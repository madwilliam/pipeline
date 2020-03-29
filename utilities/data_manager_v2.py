import os, sys
import json
import numpy as np
import pandas as pd
import bloscpack as bp
import pickle
import shutil
from skimage.io import imread
from metadata import ROOT_DIR, convert_resolution_string_to_voxel_size, SECTION_THICKNESS
from utilities2015 import load_ini, load_hdf_v2, one_liner_to_arr


class DataManager(object):
    metadata_cache = {}

    def __init__(self):
        """ setup the attributes for the data manager
        """
        self.metadata_cache = self.generate_metadata_cache()

    def generate_metadata_cache(self):

        all_stacks = os.listdir(ROOT_DIR)
        self.metadata_cache['image_shape'] = {}
        self.metadata_cache['anchor_fn'] = {}
        self.metadata_cache['sections_to_filenames'] = {}
        self.metadata_cache['filenames_to_sections'] = {}
        self.metadata_cache['section_limits'] = {}
        self.metadata_cache['cropbox'] = {}
        self.metadata_cache['valid_sections'] = {}
        self.metadata_cache['valid_filenames'] = {}
        self.metadata_cache['valid_sections_all'] = {}
        self.metadata_cache['valid_filenames_all'] = {}
        for stack in all_stacks:
            # Don't print out long error messages if base folder not found
            if not os.path.exists(DataManager.get_images_root_folder(stack)):
                # sys.stderr.write("Folder for stack %s not found, skipping.\n" % (stack))
                continue
            # Try to load metadata_cache.json file before doing anything else
            try:
                with open(os.path.join(ROOT_DIR, stack, 'brains_info', 'metadata_cache.json')) as json_file:
                    saved_metadata = json.load(json_file)
                for key in saved_metadata.keys():
                    # The metadata_cache json file has extraneous keys. (currently only "stack")
                    if key == 'stack':
                        continue
                    if key == 'sections_to_filenames':
                        self.metadata_cache[key][stack] = {int(k): v for k, v in saved_metadata[key].items()}
                    else:
                        self.metadata_cache[key][stack] = saved_metadata[key]
                print('Loaded data from saved metadata_cache for ' + stack)
                continue
            except:
                pass

            try:
                self.metadata_cache['anchor_fn'][stack] = DataManager.load_anchor_filename(stack)
            except Exception as e:
                sys.stderr.write("Failed to cache %s anchor: %s\n" % (stack, e))
                pass

            try:
                self.metadata_cache['sections_to_filenames'][stack] = DataManager.load_sorted_filenames(stack)[1]
                print('self.metadata_cache[sections_to_filenames][stack]',
                      self.metadata_cache['sections_to_filenames'][stack])
            except Exception as e:
                print('could not load sections to filenames')
                sys.stderr.write("Failed to cache %s sections_to_filenames: %s\n" % (stack, e))
                pass

            try:
                self.metadata_cache['filenames_to_sections'][stack] = DataManager.load_sorted_filenames(stack)[0]
                if 'Placeholder' in self.metadata_cache['filenames_to_sections'][stack]:
                    self.metadata_cache['filenames_to_sections'][stack].pop('Placeholder')
                if 'Nonexisting' in self.metadata_cache['filenames_to_sections'][stack]:
                    self.metadata_cache['filenames_to_sections'][stack].pop('Nonexisting')
                if 'Rescan' in self.metadata_cache['filenames_to_sections'][stack]:
                    self.metadata_cache['filenames_to_sections'][stack].pop('Rescan')
            except Exception as e:
                sys.stderr.write("Failed to cache %s filenames_to_sections: %s\n" % (stack, e))
                pass

            try:
                self.metadata_cache['section_limits'][stack] = DataManager.load_section_limits(stack, operation=2)
            except Exception as e:
                sys.stderr.write("Failed to cache %s section_limits: %s\n" % (stack, e))
                pass

            try:
                # alignedBrainstemCrop cropping box relative to alignedpadded
                self.metadata_cache['cropbox'][stack] = DataManager.load_cropbox(stack, operation=2)
            except Exception as e:
                sys.stderr.write("Failed to cache %s cropbox: %s\n" % (stack, e))
                pass

            try:
                first_sec, last_sec = self.metadata_cache['section_limits'][stack]
                self.metadata_cache['valid_sections'][stack] = [sec for sec in range(first_sec, last_sec + 1) \
                                                                if sec in self.metadata_cache['sections_to_filenames'][
                                                                    stack] and \
                                                                not self.is_invalid(stack=stack, sec=sec)]
                self.metadata_cache['valid_filenames'][stack] = [
                    self.metadata_cache['sections_to_filenames'][stack][sec] for sec
                    in
                    self.metadata_cache['valid_sections'][stack]]
            except Exception as e:
                sys.stderr.write("Failed to cache %s valid_sections/filenames: %s\n" % (stack, e))
                pass

            try:
                self.metadata_cache['valid_sections_all'][stack] = [sec for sec, fn in
                                                                    self.metadata_cache['sections_to_filenames'][
                                                                        stack].iteritems() if
                                                                    not self.is_invalid(fn=fn)]
                self.metadata_cache['valid_filenames_all'][stack] = [fn for sec, fn in
                                                                     self.metadata_cache['sections_to_filenames'][
                                                                         stack].iteritems() if
                                                                     not self.is_invalid(fn=fn)]
            except:
                pass

            try:
                self.metadata_cache['image_shape'][stack] = DataManager.get_image_dimension(stack)
            except Exception as e:
                sys.stderr.write("Failed to cache %s image_shape: %s\n" % (stack, e))
                pass

        return self.metadata_cache

    def copy_over_tif_files(self, stack):
        input_tifs = os.listdir(os.path.join(ROOT_DIR, stack, 'tif'))

        # Make STACKNAME_raw/ folder
        try:
            os.makedirs(ROOT_DIR, stack, 'raw')
        except Exception as e:
            # print(e)
            pass

        filenames_list = DataManager.load_sorted_filenames(stack)[0].keys()
        # Copy over tiff files in the selected folder which match sorted_filenames.txt
        for filename in filenames_list:
            for input_tif in input_tifs:
                if filename in input_tif:
                    source = os.path.join(ROOT_DIR, stack, 'tif', input_tif)
                    destination = os.path.join(ROOT_DIR, stack, 'raw', input_tif)
                    shutil.copyfile(source, destination)

    @staticmethod
    def get_brain_info_root_folder(stack):
        return os.path.join(ROOT_DIR, stack, 'brains_info')

    @staticmethod
    def get_brain_info_metadata_fp(stack):
        return os.path.join(ROOT_DIR, stack, 'brains_info', 'metadata.ini')

    @staticmethod
    def get_brain_info_metadata(stack):
        fp = DataManager.get_brain_info_metadata_fp(stack)
        contents_dict = load_ini(fp)
        if contents_dict is None:
            sys.stderr.write('No brain_info_metadata')
            return None
        else:
            return contents_dict

    @staticmethod
    def get_brain_info_progress_fp(stack):
        return os.path.join(ROOT_DIR, stack, 'brains_info', 'progress.ini')

    @staticmethod
    def get_brain_info_progress(stack):
        fp = DataManager.get_brain_info_progress_fp(stack)
        print('test fp ', fp)
        contents_dict = load_ini(fp)
        if contents_dict is None:
            sys.stderr.write('No brain_info_progress')
            return None
        else:
            return contents_dict

    @staticmethod
    def load_sorted_filenames(stack, fp=None, redownload=False):
        """
        Get the mapping between section index and image filename.

        Returns:
            filename_to_section, section_to_filename
        """

        if fp is None:
            assert stack is not None, 'Must specify stack'
            fp = DataManager.get_sorted_filenames_filename(stack=stack)
        print('load sorted', fp)

        # download_from_s3(fp, local_root=THUMBNAIL_DATA_ROOTDIR, redownload=redownload)
        filename_to_section, section_to_filename = DataManager.load_data(fp, filetype='file_section_map')
        if 'Placeholder' in filename_to_section:
            filename_to_section.pop('Placeholder')
        return filename_to_section, section_to_filename

    @staticmethod
    def load_data(filepath, filetype=None):

        if not os.path.exists(filepath):
            sys.stderr.write('File does not exist: %s\n' % filepath)

        if filetype == 'bp':
            return bp.unpack_ndarray_file(filepath)
        elif filetype == 'npy':
            return np.load(filepath)
        elif filetype == 'image':
            return imread(filepath)
        elif filetype == 'hdf':
            try:
                return pd.load_hdf(filepath)
            except:
                return load_hdf_v2(filepath)
        elif filetype == 'bbox':
            return np.loadtxt(filepath).astype(np.int)
        elif filetype == 'annotation_hdf':
            contour_df = pd.read_hdf(filepath, 'contours')
            return contour_df
        elif filetype == 'pickle':
            return pickle.load(open(filepath, 'r'))
        elif filetype == 'file_section_map':
            with open(filepath, 'r') as f:
                fn_idx_tuples = [line.strip().split() for line in f.readlines()]
                filename_to_section = {fn: int(idx) for fn, idx in fn_idx_tuples}
                section_to_filename = {int(idx): fn for fn, idx in fn_idx_tuples}
            return filename_to_section, section_to_filename
        elif filetype == 'label_name_map':
            label_to_name = {}
            name_to_label = {}
            with open(filepath, 'r') as f:
                for line in f.readlines():
                    name_s, label = line.split()
                    label_to_name[int(label)] = name_s
                    name_to_label[name_s] = int(label)
            return label_to_name, name_to_label
        elif filetype == 'anchor':
            with open(filepath, 'r') as f:
                anchor_fn = f.readline().strip()
            return anchor_fn
        elif filetype == 'transform_params':
            with open(filepath, 'r') as f:
                lines = f.readlines()

                global_params = one_liner_to_arr(lines[0], float)
                centroid_m = one_liner_to_arr(lines[1], float)
                xdim_m, ydim_m, zdim_m = one_liner_to_arr(lines[2], int)
                centroid_f = one_liner_to_arr(lines[3], float)
                xdim_f, ydim_f, zdim_f = one_liner_to_arr(lines[4], int)

            return global_params, centroid_m, centroid_f, xdim_m, ydim_m, zdim_m, xdim_f, ydim_f, zdim_f
        elif filepath.endswith('ini'):
            fp = "WTF"  # EOD, 3/25/2020 i have no idea what fp is supposed to be set to
            return load_ini(fp)
        else:
            sys.stderr.write('File type %s not recognized.\n' % filetype)

    @staticmethod
    def get_sorted_filenames_filename(stack):
        fn = os.path.join(ROOT_DIR, stack, 'brains_info', 'sorted_filenames.txt')
        return fn

    @staticmethod
    def get_image_filepath(stack, version=None, resol=None,
                           section=None, fn=None, ext=None, sorted_filenames_fp=None):
        """
        Args:
            version (str): the version string.

        Returns:
            Absolute path of the image file.
        """
        print('stack is ', stack, type(stack))
        data_dir = os.path.join(ROOT_DIR, stack, 'tif')
        thumbnail_data_dir = os.path.join(ROOT_DIR, stack, 'thumbnail')
        if section is not None:
            try:
                DataManager.metadata_cache['sections_to_filenames'][stack]
            except:
                sys.stderr.write(
                    'No sorted filenames could be loaded for {}. May not have been set up correctly.'.format(stack))
                return

            if sorted_filenames_fp is not None:
                _, sections_to_filenames = DataManager.load_sorted_filenames(fp=sorted_filenames_fp)
                if section not in sections_to_filenames:
                    raise Exception('Section %d is not specified in sorted list.' % section)
                fn = sections_to_filenames[section]
            else:
                if section not in DataManager.metadata_cache['sections_to_filenames'][stack]:
                    raise Exception('Section %d is not specified in sorted list.' % section)
                fn = DataManager.metadata_cache['sections_to_filenames'][stack][section]

            if DataManager.is_invalid(fn=fn, stack=stack):
                raise Exception('Section is invalid: %s.' % fn)
        else:
            assert fn is not None

        image_dir = DataManager.get_image_dir(stack=stack, resol=resol, version=version)
        image_dir = os.path.join(ROOT_DIR, stack, 'raw')
        if version is None:
            image_name = '{}_{}_{}.tif'.format(fn, stack, resol)
        else:
            if ext is None:
                if version == 'mask':
                    ext = 'png'
                elif version == 'contrastStretched' or version.endswith('Jpeg') or version == 'jpeg':
                    ext = 'jpg'
                else:
                    ext = 'tif'
            image_name = '{}_{}_{}_{}.{}'.format(fn, stack, resol, version, ext)

        image_path = os.path.join(image_dir, image_name)
        return image_path

    ######################################################################################################################
    #                                     ROOT FOLDERS                                                                   #
    ######################################################################################################################

    @staticmethod
    def get_images_root_folder(stack):
        # return os.path.join( os.environ['ROOT_DIR'], stack, 'preprocessing_data' )
        return os.path.join(ROOT_DIR, stack, 'tif')

    @staticmethod
    def get_image_dir(stack, version=None, resol=None):
        """
        Args:
            version (str): version string
        Returns:
            Absolute path of the image directory.
        """
        data_dir = ROOT_DIR
        print('stack is ', stack, type(stack))

        if resol == 'thumbnail' or resol == 'down64':
            image_dir = os.path.join(ROOT_DIR, stack, 'thumbnail')
        else:
            image_dir = os.path.join(ROOT_DIR, stack, 'tif')

        return image_dir

    @staticmethod
    def setup_get_raw_fp(stack):
        return os.path.join(ROOT_DIR, stack, 'raw')

    @staticmethod
    def setup_get_thumbnail_fp(stack):
        return os.path.join(ROOT_DIR, stack, 'thumbnail')

    @staticmethod
    def setup_get_raw_fp_secondary_channel(stack, channel):
        return os.path.join(ROOT_DIR, stack, '{}'.format(channel))

    """
    Note: 3/27/2020, stack and prep_id are sometimes the same variable.
    stack is prep_id from the database.
    For the method below, the original argument was prep_id, which i have 
    changed to operation
    """

    @staticmethod
    def get_image_dimension(stack, operation='alignedBrainstemCrop'):
        """
        Returns the dimensions at raw resolution for the alignedBrainstemCrop images.

        Returns:
            (raw image width, raw image height)
        """

        # first_sec, last_sec = DataManager.load_cropbox(stack)[4:]
        # anchor_fn = DataManager.load_anchor_filename(stack)
        # filename_to_section, section_to_filename = DataManager.load_sorted_filenames(stack)

        xmin, xmax, ymin, ymax = DataManager.load_cropbox(stack)
        return (xmax - xmin + 1) * 32, (ymax - ymin + 1) * 32

    @staticmethod
    def load_section_limits(stack, operation):
        """
        """

        d = DataManager.load_data(DataManager.get_section_limits_filename(stack))
        return np.r_[d['left_section_limit'], d['right_section_limit']]

    @staticmethod
    def get_section_limits_filename(stack):
        """
        Return path to file that specified the cropping box of the given crop specifier.

        Args:
            stack animal identifier
        """

        fp = os.path.join(ROOT_DIR, stack, 'brains_info', 'sectionLimits.json')
        if not os.path.exists(fp):
            fp = os.path.join(ROOT_DIR, stack, 'brains_info', 'sectionLimits.ini')

        return fp

    @staticmethod
    def load_cropbox(stack, anchor_fn=None, convert_section_to_z=False, operation=2,
                     return_origin_instead_of_bbox=False,
                     return_dict=False, only_2d=True):
        """
        Loads the cropping box for the given crop at thumbnail (downsample 32 times from raw) resolution.

        Args:
            convert_section_to_z (bool): If true, return (xmin,xmax,ymin,ymax,zmin,zmax) where z=0 is section #1; if false, return (xmin,xmax,ymin,ymax,secmin,secmax)
            operation (int)
        """

        if isinstance(operation, str):
            fp = DataManager.get_cropbox_filename(stack)
        elif isinstance(operation, int):
            # fp = DataManager.get_cropbox_filename(stack=stack, anchor_fn=anchor_fn, operation=operation)
            fp = DataManager.get_cropbox_filename(stack)
        else:
            raise Exception("operation %s must be either str or int" % operation)

        if not os.path.exists(fp):
            # sys.stderr.write("Seems you are using operation INIs to provide cropbox.\n")
            if operation == 2 or operation == 'alignedBrainstemCrop':
                fp = os.path.join(ROOT_DIR, stack, 'brains_info', 'from_padded_to_brainstem.ini')
            elif operation == 5 or operation == 'alignedWithMargin':
                fp = os.path.join(ROOT_DIR, stack, 'brains_info', 'from_padded_to_wholeslice.ini')
            else:
                raise Exception("Not implemented")
        else:
            print('TESTING')
            # raise Exception("Cannot find any cropbox specification.")
            # download_from_s3(fp, local_root=THUMBNAIL_DATA_ROOTDIR)

        if fp.endswith('.txt'):
            xmin, xmax, ymin, ymax, secmin, secmax = DataManager.load_data(fp).astype(np.int)

            if convert_section_to_z:
                zmin = int(
                    DataManager.convert_section_to_z(stack=stack, sec=secmin, downsample=32, z_begin=0, mid=True))
                zmax = int(
                    DataManager.convert_section_to_z(stack=stack, sec=secmax, downsample=32, z_begin=0, mid=True))

        elif fp.endswith('.json') or fp.endswith('.ini'):
            if fp.endswith('.json'):
                cropbox_dict = DataManager.load_data(fp)
            else:

                if fp.endswith('cropbox.ini'):
                    cropbox_dict = load_ini(fp, section=operation)
                elif '_to_' in fp:
                    cropbox_dict = load_ini(fp)
                else:
                    raise Exception("Do not know how to parse %s for cropbox" % fp)

        assert cropbox_dict['resolution'] == 'thumbnail', "Provided cropbox must have thumbnail resolution."

        xmin = cropbox_dict['rostral_limit']
        xmax = cropbox_dict['caudal_limit']
        ymin = cropbox_dict['dorsal_limit']
        ymax = cropbox_dict['ventral_limit']

        if 'left_limit_section_number' in cropbox_dict:
            secmin = cropbox_dict['left_limit_section_number']
        else:
            secmin = None

        if 'right_limit_section_number' in cropbox_dict:
            secmax = cropbox_dict['right_limit_section_number']
        else:
            secmax = None

        if 'left_limit' in cropbox_dict:
            zmin = cropbox_dict['left_limit']
        else:
            zmin = None

        if 'right_limit' in cropbox_dict:
            zmax = cropbox_dict['right_limit']
        else:
            zmax = None

        if return_dict:
            if convert_section_to_z:
                cropbox_dict = {'rostral_limit': xmin,
                                'caudal_limit': xmax,
                                'dorsal_limit': ymin,
                                'ventral_limit': ymax,
                                'left_limit': zmin,
                                'right_limit': zmax}
            else:
                cropbox_dict = {'rostral_limit': xmin,
                                'caudal_limit': xmax,
                                'dorsal_limit': ymin,
                                'ventral_limit': ymax,
                                'left_limit_section_number': secmin,
                                'right_limit_section_number': secmax}
            return cropbox_dict

        else:
            if convert_section_to_z:
                cropbox = np.array((xmin, xmax, ymin, ymax, zmin, zmax))
                if return_origin_instead_of_bbox:
                    return cropbox[[0, 2, 4]].astype(np.int)
                else:
                    if only_2d:
                        return cropbox[:4].astype(np.int)
                    else:
                        return cropbox.astype(np.int)
            else:
                assert not return_origin_instead_of_bbox
                cropbox = np.array((xmin, xmax, ymin, ymax, secmin, secmax))
                print(cropbox)
                if only_2d:
                    return cropbox[:4].astype(np.int)
                else:
                    return cropbox.astype(np.int)

    @staticmethod
    def get_auto_submask_dir_filepath(stack, fn=None, sec=None):
        submasks_dir = DataManager.get_auto_submask_rootdir_filepath(stack)
        if fn is None:
            fn = DataManager.metadata_cache['sections_to_filenames'][stack][sec]
        dir_path = os.path.join(submasks_dir, fn)
        return dir_path

    @staticmethod
    def get_auto_submask_rootdir_filepath(stack):
        return os.path.join(ROOT_DIR, stack, 'prep1', 'thumbnail_autoSubmasks')

    @staticmethod
    def get_auto_submask_filepath(stack, what, submask_ind=None, fn=None, sec=None):
        """
        Args:
            what (str): submask or decisions.
            submask_ind (int): if what is submask, must provide submask_ind.
        """
        dir_path = DataManager.get_auto_submask_dir_filepath(stack=stack, fn=fn, sec=sec)

        if what == 'submask':
            assert submask_ind is not None, "Must provide submask_ind."
            fp = os.path.join(dir_path, fn + '_prep1_thumbnail_autoSubmask_%d.png' % submask_ind)
        elif what == 'decisions':
            fp = os.path.join(dir_path, fn + '_prep1_thumbnail_autoSubmaskDecisions.csv')
        else:
            raise Exception("Input %s is not recognized." % what)

        return fp

    @staticmethod
    def get_intensity_normalization_result_filepath(what, stack, fn=None, section=None):

        if fn is None:
            fn = DataManager.metadata_cache['sections_to_filenames'][stack][section]
            if DataManager.is_invalid(fn=fn):
                raise Exception('Section is invalid: %s.' % fn)

        if what == 'region_centers':
            fp = os.path.join(DataManager.get_images_root_folder(stack), stack + '_intensity_normalization_results',
                              'regionCenters',
                              stack + '_' + fn + '_raw_regionCenters.npy')
        elif what == 'mean_std_all_regions':
            fp = os.path.join(DataManager.get_images_root_folder(stack), stack + '_intensity_normalization_results',
                              'meanStdAllRegions',
                              stack + '_' + fn + '_raw_meanStdAllRegions.npy')
        elif what == 'mean_map':
            fp = os.path.join(DataManager.get_images_root_folder(stack), stack + '_intensity_normalization_results',
                              'meanMap',
                              stack + '_' + fn + '_raw_meanMap.npy')
        elif what == 'std_map':
            fp = os.path.join(DataManager.get_images_root_folder(stack), stack + '_intensity_normalization_results',
                              'stdMap',
                              stack + '_' + fn + '_raw_stdMap.npy')
        elif what == 'float_histogram_png':
            fp = os.path.join(DataManager.get_images_root_folder(stack), stack + '_intensity_normalization_results',
                              'floatHistogram',
                              stack + '_' + fn + '_raw_floatHistogram.png')
        elif what == 'normalized_float_map':
            fp = os.path.join(DataManager.get_images_root_folder(stack), stack + '_intensity_normalization_results',
                              'normalizedFloatMap',
                              stack + '_' + fn + '_raw_normalizedFloatMap.npy')
        elif what == 'float_percentiles':
            fp = os.path.join(DataManager.get_images_root_folder(stack), stack + '_intensity_normalization_results',
                              'floatPercentiles',
                              stack + '_' + fn + '_raw_floatPercentiles.npy')
        else:
            raise Exception("what = %s is not recognized." % what)

        return fp

    @staticmethod
    def get_anchor_filename_filename(stack):
        fn = os.path.join(ROOT_DIR, stack, 'brains_info', 'anchor.txt')
        return fn

    @staticmethod
    def get_anchor_filename_filename_v2(stack):
        fp = os.path.join(ROOT_DIR, stack, 'brains_info', 'from_none_to_aligned.ini')
        return fp

    @staticmethod
    def load_anchor_filename(stack):
        fp = DataManager.get_anchor_filename_filename(stack)
        if not os.path.exists(fp):
            # sys.stderr.write("No anchor.txt is found. Seems we are using the operation ini to provide anchor. Try to load operation ini.\n")
            fp = DataManager.get_anchor_filename_filename_v2(stack)  # ini
            anchor_image_name = load_ini(fp)['anchor_image_name']
        else:
            # download_from_s3(fp, local_root=THUMBNAIL_DATA_ROOTDIR)
            anchor_image_name = DataManager.load_data(fp, filetype='anchor')
        return anchor_image_name

    @staticmethod
    def get_cropbox_filename(stack):
        """
        Return path to file that specified the cropping box of the given crop specifier.

        Args:
            stack animal identifier
        """

        fp = os.path.join(ROOT_DIR, stack, 'brains_info', 'cropbox.ini')
        return fp

    @staticmethod
    # def convert_section_to_z(sec, downsample=None, resolution=None, stack=None, first_sec=None, mid=False):
    def convert_section_to_z(sec, downsample=None, resolution=None, stack=None, mid=False, z_begin=None,
                             first_sec=None):
        """
        Voxel size is determined by `resolution`.

        z = sec * section_thickness_in_unit_of_cubic_voxel_size - z_begin

        Physical size of a cubic voxel depends on the downsample factor.

        Args:
            downsample/resolution: this determines the voxel size.
            z_begin (float): z-coordinate of an origin. The z-coordinate of a given section is relative to this value.
                Default is the z position of the `first_sec`. This must be consistent with `downsample`.
            first_sec (int): Index of the section that defines z=0.
                Default is the first brainstem section defined in ``cropbox".
                If `stack` is given, the default is the first section of the brainstem.
                If `stack` is not given, default = 1.
            mid (bool): If false, return the z-coordinates of the two sides of the section. If true, only return a single scalar = the average.

        Returns:
            z1, z2 (2-tuple of float): the z-levels of the beginning and end of the queried section, counted from `z_begin`.
        """

        if downsample is not None:
            resolution = 'down%d' % downsample

        voxel_size_um = convert_resolution_string_to_voxel_size(resolution=resolution, stack=stack)
        section_thickness_in_voxel = SECTION_THICKNESS / voxel_size_um  # Voxel size in z direction in unit of x,y pixel.
        # if first_sec is None:
        #     # first_sec, _ = DataManager.load_cropbox(stack)[4:]
        #     if stack is not None:
        #         first_sec = metadata_cache['section_limits'][stack][0]
        #     else:
        #         first_sec = 1
        #

        if z_begin is None:
            if first_sec is not None:
                z_begin = (first_sec - 1) * section_thickness_in_voxel
            else:
                z_begin = 0

        z1 = (sec - 1) * section_thickness_in_voxel
        z2 = sec * section_thickness_in_voxel
        # print "z1, z2 =", z1, z2

        if mid:
            return np.mean([z1 - z_begin, z2 - 1 - z_begin])
        else:
            return z1 - z_begin, z2 - 1 - z_begin

    @staticmethod
    def convert_z_to_section(z, downsample=None, resolution=None, z_first_sec=None, sec_z0=None, stack=None):
        """
        Convert z coordinate to section index.

        Args:
            resolution (str): planar resolution
            z_first_sec (int): z level of section index 1. Provide either this or `sec_z0`.
            sec_z0 (int): section index at z=0. Provide either this or `z_first_sec`.
        """

        if downsample is not None:
            resolution = 'down%d' % downsample

        voxel_size_um = convert_resolution_string_to_voxel_size(resolution=resolution, stack=stack)
        section_thickness_in_voxel = SECTION_THICKNESS / voxel_size_um

        if z_first_sec is not None:
            sec_float = np.float32(
                (z - z_first_sec) / section_thickness_in_voxel)  # if use np.float, will result in np.floor(98.0)=97
        elif sec_z0 is not None:
            sec_float = np.float32(z / section_thickness_in_voxel) + sec_z0
        else:
            sec_float = np.float32(z / section_thickness_in_voxel)

        # print "sec_float =", sec_float
        sec = int(np.ceil(sec_float))
        return sec

    @staticmethod
    def is_invalid(fn=None, sec=None, stack=None):
        """
        Determine if a section is invalid (i.e. tagged nonexisting, rescan or placeholder in the brain labeling GUI).
        """
        if sec is not None:
            assert stack is not None, 'is_invalid: if section is given, stack must not be None.'
            if sec not in DataManager.metadata_cache['sections_to_filenames'][stack]:
                return True
            fn = DataManager.metadata_cache['sections_to_filenames'][stack][sec]
        else:
            assert fn is not None, 'If sec is not provided, must provide fn'
        return fn in ['Nonexisting', 'Rescan', 'Placeholder']
