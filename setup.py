from setuptools import setup

setup(
    name='mdns_repeater',
    version='0.1.0',
    author='Kyle Rose',
    author_email='krose@krose.org',
    license='MIT',
    packages=['mdns_repeater'],
    install_requires=[],
    entry_points={
        'console_scripts': [
            'mdns_repeater = mdns_repeater:main',
        ],
    },
)
