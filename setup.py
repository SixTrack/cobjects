from setuptools import setup

setup(
        name='cobjects',
        version='0.0.10',
        description='Manage C data from Python for C libraries',
        author='Riccardo De Maria',
        author_email='riccardo.de.maria@cern.ch',
        url='https://github.com/rdemaria/cobjects',
        python_requires='>=3.6',
        setup_requires=['cffi>=1.0.0'],
        install_requires=['numpy','cffi>=1.0.0'],
        packages=['cobjects','src','_cffi_builder'], #dir to include
#       package_dir={'cobjects': 'cobjects'}, # not needed
        package_data={'src':['*.h','*.c']}, #.h ignored by cffi
        cffi_modules=["_cffi_builder/cbuffer_builder.py:ffibuilder"],
)
