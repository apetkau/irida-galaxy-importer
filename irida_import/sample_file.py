class SampleFile:

    """A representation of a sample file obtained from IRIDA"""

    def __init__(self, name, path):
        """
        Create a sample file instance.

        :type name: str
        :param name: the name of the sample file
        :type path: str
        :param path: the URI of the sample file
        """

        self.path = path
        self.name = name
        self.library_dataset_id = None

    def __eq__(self, sample_file):
        equal = False

        try:
            if self.path == sample_file.path:
                equal = True
        except AttributeError:
            pass

        return equal

    def __repr__(self):
        return self.name + " @ " + self.path

    def state(self, gi):
        return gi.datasets.show_dataset(self.library_dataset.id, hda_ldda='ldda')['state']

    def delete(self, gi, library_id):
        return gi.libraries.delete_library_dataset(library_id, self.library_dataset.id, purged=True)['deleted']
