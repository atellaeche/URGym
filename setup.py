from setuptools import setup, find_packages

setup(
    name='urgym',
    version='0.0.3',
    packages=find_packages(include=["urgym", "urgym.*"]),
    include_package_data=True,  # Ensures non-Python files are included
    package_data={
        "urgym": ["meshes/**/*", "urdf/**/*"],  # Include all files within these folders
    },
    install_requires=[
        'numpy==1.26.4',
        'gymnasium==0.29.1',
        'pybullet'
    ],
    author='Inaki Vazquez',
    author_email='ivazquez@deusto.es',
    description='A set of Pybullet-based Gymnasium compatible environments for Universal Robots UR5',
    url='https://github.com/inakivazquez/urgym',
)