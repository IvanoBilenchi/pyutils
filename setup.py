from setuptools import find_packages, setup

setup(name='cli-pyutils',
      version='0.1',
      description='Collection of useful Python modules for CLI tools.',
      author='Ivano Bilenchi',
      author_email='ivanobilenchi@gmail.com',
      url='https://github.com/IvanoBilenchi/pyutils',
      packages=find_packages(),
      install_requires=['psutil']
      )
