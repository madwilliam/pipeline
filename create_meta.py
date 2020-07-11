import argparse
from utilities.sqlcontroller import SqlController
from controller.preprocessor import SlideProcessor
from sql_setup import session, CZI_FILES_ARE_SCANNED_TO_GET_METADATA


def make_meta(animal):
    """
    Scans the czi dir to extract the meta information for each tif file
    Args:
        animal: the animal as primary key

    Returns: nothing
    """
    slide_processor = SlideProcessor(animal, session)
    sqlController = SqlController(animal)
    slide_processor.process_czi_dir()
    sqlController.set_task(animal, CZI_FILES_ARE_SCANNED_TO_GET_METADATA)

if __name__ == '__main__':
    # Parsing argument
    parser = argparse.ArgumentParser(description='Work on Animal')
    parser.add_argument('--animal', help='Enter the animal', required=True)
    args = parser.parse_args()
    animal = args.animal
    make_meta(animal)