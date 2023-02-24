import contextlib
import functools
import os

# import shutil
import tempfile

from django.conf import settings

tmp = os.path.join(settings.GLOBAL_SETTINGS['SHARED_PARTITION'], 'tmp')


@contextlib.contextmanager
def tmpdir(cleanup=True):
    # Make the temp dir underneath tmp_root config setting
    root = os.path.abspath(tmp)
    try:
        os.makedirs(root)
    except OSError:
        if not os.path.isdir(root):
            raise
    path = tempfile.mkdtemp(dir=root)

    try:
        yield path
    finally:
        # Cleanup the temp dir
        # if cleanup and os.path.isdir(path):
        #     shutil.rmtree(path)
        pass


def with_tmpdir(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        if '_tempdir' in kwargs:
            return fn(*args, **kwargs)

        cleanup = kwargs.get('cleanup', True)
        with tmpdir(cleanup=cleanup) as tempdir:
            kwargs['_tmp'] = tmp
            kwargs['_tempdir'] = tempdir
            return fn(*args, **kwargs)
    return wrapped
