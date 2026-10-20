import sys
import codecs
import setuptools

from version import __version__ as version


install_requires = [
    'beautifulsoup4',
    'decorator',
    'kitchen',
    'requests >=2.4.0',  # https://github.com/michael-lazar/rtv/issues/325
    'six',
]

tests_require = [
    'coveralls',
    'pytest>=3.1.0',  # Pinned for the ``pytest.param`` method
    'coverage',
    'mock',
    'pylint',
    'responses',
]

extras_require = {
    'test': tests_require
}

# https://hynek.me/articles/conditional-python-dependencies/
if int(setuptools.__version__.split(".", 1)[0]) < 18:
    assert "bdist_wheel" not in sys.argv
    if sys.version_info[0:2] < (3, 6):
        install_requires.append("mailcap-fix")
else:
    # Building the bdist_wheel with conditional environment dependencies
    # requires setuptools version > 18. For older setuptools versions this
    # will raise an error.
    extras_require.update({":python_version<'3.6'": ["mailcap-fix"]})


def long_description():
    with codecs.open('README.md', encoding='utf8') as f:
        return f.read()


setuptools.setup(
    name='tuil',
    version=version,
    description='A terminal-first Lemmy reader (based on tuir)',
    long_description=long_description(),
    long_description_content_type='text/markdown',
    url='https://github.com/faethon/tuil',
    author='tuil contributors',
    author_email='',
    license='GPL-3.0-only',
    keywords='lemmy fediverse terminal curses',
    packages=[
        'tuil',
        'tuil.packages',
        'tuil.packages.mailcap',
        'tuil.api',
    ],
    package_data={
        'tuil': ['templates/*', 'themes/*'],
    },
    data_files=[("share/man/man1", ["tuil.1"])],
    install_requires=install_requires,
    tests_require=tests_require,
    extras_require=extras_require,
    entry_points={'console_scripts': ['tuil=tuil.__main__:main']},
    classifiers=[
        'Intended Audience :: End Users/Desktop',
        'Environment :: Console :: Curses',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX',
        'Natural Language :: English',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
        'Programming Language :: Python :: 3.15',
        'Topic :: Terminals',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content :: Message Boards',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content :: News/Diary',
        ],
)
