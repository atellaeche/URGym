from setuptools import setup, find_packages

setup(
    name='urgym',
    version='0.0.2',
    packages=find_packages(),
    install_requires=[
        'numpy==2.2.3',
        'gymnasium==1.0.0',
        'pybullet'
    ],
    author='Inaki Vazquez',
    author_email='ivazquez@deusto.es',
    description='A set of Pybullet-based Gymnasium compatible environments for Universal Robots UR5',
    url='https://github.com/inakivazquez/urgym',
)
