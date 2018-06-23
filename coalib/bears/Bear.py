import cProfile
import inspect
import itertools
import pstats
import tempfile
import traceback
import os
from functools import partial
from os import makedirs, fdopen, remove
from os.path import join, abspath, exists
from termcolor import colored, cprint
from terminaltables import AsciiTable
import requests
from appdirs import user_data_dir

from pyprint.Printer import Printer

from coala_utils.decorators import (enforce_signature, classproperty,
                                    get_public_members)

from coalib.bears.BEAR_KIND import BEAR_KIND
from coalib.output.printers.LogPrinter import LogPrinterMixin
from coalib.results.Result import Result
from coalib.results.TextPosition import ZeroOffsetError
from coalib.settings.FunctionMetadata import FunctionMetadata
from coalib.settings.Section import Section
from coalib.settings.ConfigurationGathering import get_config_directory

from .meta import bearclass


class Bear(Printer, LogPrinterMixin, metaclass=bearclass):
    """
    A bear contains the actual subroutine that is responsible for checking
    source code for certain specifications. However it can actually do
    whatever it wants with the files it gets. If you are missing some Result
    type, feel free to contact us and/or help us extending the coalib.

    This is the base class for every bear. If you want to write a bear, you
    will probably want to look at the GlobalBear and LocalBear classes that
    inherit from this class. In any case you'll want to overwrite at least the
    run method. You can send debug/warning/error messages through the
    debug(), warn(), err() functions. These will send the
    appropriate messages so that they are outputted. Be aware that if you use
    err(), you are expected to also terminate the bear run-through
    immediately.

    Settings are available at all times through self.section.

    To indicate which languages your bear supports, just give it the
    ``LANGUAGES`` value which should be a set of string(s):

    >>> from dependency_management.requirements.PackageRequirement import (
    ... PackageRequirement)
    >>> from dependency_management.requirements.PipRequirement import (
    ... PipRequirement)
    >>> class SomeBear(Bear):
    ...     LANGUAGES = {'C', 'CPP','C#', 'D'}

    To indicate the requirements of the bear, assign ``REQUIREMENTS`` a set
    with instances of ``PackageRequirements``.

    >>> class SomeBear(Bear):
    ...     REQUIREMENTS = {
    ...         PackageRequirement('pip', 'coala_decorators', '0.2.1')}

    If your bear uses requirements from a manager we have a subclass from,
    you can use the subclass, such as ``PipRequirement``, without specifying
    manager:

    >>> class SomeBear(Bear):
    ...     REQUIREMENTS = {PipRequirement('coala_decorators', '0.2.1')}

    To specify additional attributes to your bear, use the following:

    >>> class SomeBear(Bear):
    ...     AUTHORS = {'Jon Snow'}
    ...     AUTHORS_EMAILS = {'jon_snow@gmail.com'}
    ...     MAINTAINERS = {'Catelyn Stark'}
    ...     MAINTAINERS_EMAILS = {'catelyn_stark@gmail.com'}
    ...     LICENSE = 'AGPL-3.0'
    ...     ASCIINEMA_URL = 'https://asciinema.org/a/80761'

    If the maintainers are the same as the authors, they can be omitted:

    >>> class SomeBear(Bear):
    ...     AUTHORS = {'Jon Snow'}
    ...     AUTHORS_EMAILS = {'jon_snow@gmail.com'}
    >>> SomeBear.maintainers
    {'Jon Snow'}
    >>> SomeBear.maintainers_emails
    {'jon_snow@gmail.com'}

    If your bear needs to include local files, then specify it giving strings
    containing relative file paths to the INCLUDE_LOCAL_FILES set:

    >>> class SomeBear(Bear):
    ...     INCLUDE_LOCAL_FILES = {'checkstyle.jar', 'google_checks.xml'}

    To keep track easier of what a bear can do, simply tell it to the CAN_FIX
    and the CAN_DETECT sets. Possible values:

    >>> CAN_DETECT = {'Syntax', 'Formatting', 'Security', 'Complexity', 'Smell',
    ... 'Unused Code', 'Redundancy', 'Variable Misuse', 'Spelling',
    ... 'Memory Leak', 'Documentation', 'Duplication', 'Commented Code',
    ... 'Grammar', 'Missing Import', 'Unreachable Code', 'Undefined Element',
    ... 'Code Simplification', 'Statistics'}
    >>> CAN_FIX = {'Syntax', ...}

    Specifying something to CAN_FIX makes it obvious that it can be detected
    too, so it may be omitted:

    >>> class SomeBear(Bear):
    ...     CAN_DETECT = {'Syntax', 'Security'}
    ...     CAN_FIX = {'Redundancy'}
    >>> list(sorted(SomeBear.can_detect))
    ['Redundancy', 'Security', 'Syntax']

    Every bear has a data directory which is unique to that particular bear:

    >>> class SomeBear(Bear): pass
    >>> class SomeOtherBear(Bear): pass
    >>> SomeBear.data_dir == SomeOtherBear.data_dir
    False

    BEAR_DEPS contains bear classes that are to be executed before this bear
    gets executed. The results of these bears will then be passed to the
    run method as a dict via the dependency_results argument. The dict
    will have the name of the Bear as key and the list of its results as
    results:

    >>> class SomeBear(Bear): pass
    >>> class SomeOtherBear(Bear):
    ...     BEAR_DEPS = {SomeBear}
    >>> SomeOtherBear.BEAR_DEPS
    {<class 'coalib.bears.Bear.SomeBear'>}

    Every bear resides in some directory which is specified by the
    source_location attribute:

    >>> class SomeBear(Bear): pass
    >>> SomeBear.source_location
    '...Bear.py'

    Every linter bear makes use of an executable tool for its operations.
    The SEE_MORE attribute provides a link to the main page of the linter
    tool:

    >>> class PyLintBear(Bear):
    ...     SEE_MORE = 'https://www.pylint.org/'
    >>> PyLintBear.SEE_MORE
    'https://www.pylint.org/'

    In the future, bears will not survive without aspects. aspects are defined
    as part of the ``class`` statement's parameter list. According to the
    classic ``CAN_DETECT`` and ``CAN_FIX`` attributes, aspects can either be
    only ``'detect'``-able or also ``'fix'``-able:

    >>> from coalib.bearlib.aspects.Metadata import CommitMessage

    >>> class aspectsCommitBear(Bear, aspects={
    ...         'detect': [CommitMessage.Shortlog.ColonExistence],
    ...         'fix': [CommitMessage.Shortlog.TrailingPeriod],
    ... }, languages=['Python']):
    ...     pass

    >>> aspectsCommitBear.aspects['detect']
    [<aspectclass 'Root.Metadata.CommitMessage.Shortlog.ColonExistence'>]
    >>> aspectsCommitBear.aspects['fix']
    [<aspectclass 'Root.Metadata.CommitMessage.Shortlog.TrailingPeriod'>]

    To indicate the bear uses raw files, set ``USE_RAW_FILES`` to True:

    >>> class RawFileBear(Bear):
    ...     USE_RAW_FILES = True
    >>> RawFileBear.USE_RAW_FILES
    True

    However if ``USE_RAW_FILES`` is enabled the Bear is in charge of managing
    the file (opening the file, closing the file, reading the file, etc).
    """

    LANGUAGES = set()
    REQUIREMENTS = set()
    AUTHORS = set()
    AUTHORS_EMAILS = set()
    MAINTAINERS = set()
    MAINTAINERS_EMAILS = set()
    PLATFORMS = {'any'}
    LICENSE = ''
    INCLUDE_LOCAL_FILES = set()
    CAN_DETECT = set()
    CAN_FIX = set()
    ASCIINEMA_URL = ''
    SEE_MORE = ''
    BEAR_DEPS = set()
    USE_RAW_FILES = False

    @classproperty
    def name(cls):
        """
        :return: The name of the bear
        """
        return cls.__name__

    @classproperty
    def can_detect(cls):
        """
        :return: A set that contains everything a bear can detect, gathering
                 information from what it can fix too.
        """
        return cls.CAN_DETECT | cls.CAN_FIX

    @classproperty
    def source_location(cls):
        """
        :return: The file path where the bear was fetched from.
        """
        return inspect.getfile(cls)

    @classproperty
    def maintainers(cls):
        """
        :return: A set containing ``MAINTAINERS`` if specified, else takes
                 ``AUTHORS`` by default.
        """
        return cls.AUTHORS if cls.MAINTAINERS == set() else cls.MAINTAINERS

    @classproperty
    def maintainers_emails(cls):
        """
        :return: A set containing ``MAINTAINERS_EMAILS`` if specified, else
                 takes ``AUTHORS_EMAILS`` by default.
        """
        return (cls.AUTHORS_EMAILS if cls.MAINTAINERS_EMAILS == set()
                else cls.MAINTAINERS_EMAILS)

    @enforce_signature
    def __init__(self,
                 section: Section,
                 message_queue,
                 timeout=0):
        """
        Constructs a new bear.

        :param section:       The section object where bear settings are
                              contained.
        :param message_queue: The queue object for messages. Can be ``None``.
        :param timeout:       The time the bear is allowed to run. To set no
                              time limit, use 0.
        :raises TypeError:    Raised when ``message_queue`` is no queue.
        :raises RuntimeError: Raised when bear requirements are not fulfilled.
        """
        Printer.__init__(self)

        if message_queue is not None and not hasattr(message_queue, 'put'):
            raise TypeError('message_queue has to be a Queue or None.')

        self.section = section
        self.message_queue = message_queue
        self.timeout = timeout

        self.setup_dependencies()
        cp = type(self).check_prerequisites()
        if cp is not True:
            error_string = ('The bear ' + self.name +
                            ' does not fulfill all requirements.')
            if cp is not False:
                error_string += ' ' + cp

            self.err(error_string)
            raise RuntimeError(error_string)

    def _print(self, output, **kwargs):
        self.debug(output)

    def log_message(self, log_message, timestamp=None, **kwargs):
        if self.message_queue is not None:
            self.message_queue.put(log_message)

    def run(self, *args, dependency_results=None, **kwargs):
        raise NotImplementedError

    def parenthesis_split(self, sentence, separator=',',
                          lparen='(', rparen=')'):
        nb_brackets = 0
        sentence = sentence.strip(separator)
        final = [0]
        try:
            for i, c in enumerate(sentence):
                if c == lparen:
                    nb_brackets += 1
                elif c == rparen:
                    nb_brackets -= 1
                elif c == separator and nb_brackets == 0:
                    final.append(i)
                if nb_brackets < 0:
                    raise ValueError('Invalid arguments to --profile-bears')
            final.append(len(sentence))
            if nb_brackets > 0:
                raise ValueError('Invalid arguments to --profile-bears')
        except ValueError as err:
            self.err(err.args[0])
            return
        return([sentence[i:j].strip(separator) for i, j in zip(final,
                                                               final[1:])])

    def pstats_config(self, prof, stream, profile_bears):
        flag = 0
        ps = pstats.Stats(prof, stream=stream)
        if len(profile_bears) > 0:
            for setting in profile_bears[0:]:
                str_setting = str(setting).lower().strip(' \n\t')
                if u'(' in str(setting):
                    args = str(setting).split('(', 1)[1].strip(
                        ' \t\n)').replace('\'', '').replace(
                        '"', '').replace(' ', '').split(',')
                if not str_setting == u'':
                    try:
                        str_setting = str_setting.split('(', 1)[0]
                        if 'args' in locals() and args != [u''] and (
                                str_setting == u'reverse_order' or
                                str_setting == u'strip_dirs'):
                            raise ValueError(
                                'The pstats method "{}" does'
                                ' not accept any arguments.'
                                'Discarding user settings.', str_setting)
                        if 'args' in locals() and args == [u''] and not (
                                str_setting == u'reverse_order' or
                                str_setting == u'strip_dirs'):
                            raise ValueError(
                                'The pstats method "{}" requires an argument',
                                str_setting)
                        flag = 1
                        if str_setting == u'reverse_order':
                            ps.reverse_order()
                        elif str_setting == u'strip_dirs':
                            ps.strip_dirs()
                        elif str_setting == u'add':
                            ps.add(*args)
                        elif str_setting == u'dump_stats':
                            ps.dump_stats(*args)
                        elif str_setting == u'sort_stats':
                            ps.sort_stats(*args)
                        elif str_setting == u'print_stats':
                            print(args)
                            ps.print_stats(*args)
                        elif str_setting == u'print_callers':
                            ps.print_callers(*args)
                        elif str_setting == u'print_callees':
                            ps.print_callees(*args)
                        elif str_setting == u'no_trim':
                            pass
                        else:
                            self.err('Unrecognized setting "{}" for pstats'
                                     ' module. Applying default '
                                     'settings'.format(str(setting)))
                            flag = 0
                            break
                    except KeyError:
                        flag = 0
                        self.err(
                            'Invalid arguments given to a pstats method.'
                            ' Applying default settings')
                        break
                    except UnboundLocalError:
                        flag = 0
                        self.err(
                            'A given pstats method requires an argument. '
                            'Applying default settings')
                        break
                    except ValueError as err:
                        flag = 0
                        self.err(str(err.args[0]).format(
                            str(err.args[1]+'()'))+'. Applying '
                                                   'default settings')
                        break
        return ps.strip_dirs().sort_stats('cumtime') if flag == 0 else ps

    def setup_profiler_table(self, prof,
                             profile_bears, check_trim: bool = False):
        fd, path = tempfile.mkstemp()
        try:
            with fdopen(fd, 'r+') as stream:
                ps = self.pstats_config(prof, stream, profile_bears)
                ps.print_stats()
                stream.flush()
                stream.seek(0)
                lines = stream.readlines()
                req_lines = []
                table_header = []
                for line in lines:
                    if ('function calls' not in line and
                        'listing order was used' not in line and
                        'Ordered by' not in line and
                            line.strip(' \n\t') != ''):
                        req_lines.append(line)
                    elif line.strip(' \n\t') != '':
                        table_header.append(line.strip())
                channel_values = [x for x in [y.split(' ') for y in
                                              req_lines] if x and not x == '\n']

                table_data = []
                final_table_data = []
                for x in channel_values:
                    table_data.append(list(filter(lambda a: a != '', x)))
                for x in table_data:
                    start = ''
                    flag = 0
                    row = []
                    for y in x:
                        if y.startswith('{'):
                            flag = 1
                        if flag == 1:
                            start = start + y + ' '
                        elif y != '':
                            t = ' '.join(y.split())
                            row.append(t.strip())
                    if start != '':
                        row.append(start.strip())
                    final_table_data.append(row)
                colored_table_data = []
                colors = ['red', 'white', 'blue', 'yellow', 'magenta', 'green']
                linter_table = []
                linter_table.append(final_table_data[0])
                if u'linter' in str(self):
                    for i in final_table_data:
                        if u'linter'.title() in i[5] or str(self.__class__.__name__) in i[5]:
                            linter_table.append(i)

                if u'linter' in str(self):
                    final_table_data = linter_table
                else:
                    final_table_data = final_table_data if check_trim else (
                        final_table_data[:15])
                for x in final_table_data:
                    row = []
                    for index, y in enumerate(x):
                        row.append(colored(y, colors[index]))
                    colored_table_data.append(row)
                table = AsciiTable(colored_table_data)
                for line in table_header:
                    print(line)
                cprint(table.table)
        finally:
            remove(path)

    def setup_profiler(self, *args, **kwargs):
        profile_output =kwargs.get('profile_output', False)
        profile_dump = kwargs.get('profile_dump', False)
        profile_commands = kwargs.get('profile_commands', False)
        if str(profile_output) is not u'False':
            profile_bears = self.parenthesis_split(str(profile_output))
        if str(profile_dump) is not u'False':
            profile_bears = self.parenthesis_split(str(profile_dump))
        if str(profile_commands) is not u'False':
            profile_bears = self.parenthesis_split(str(profile_commands))
        if (str(profile_output) is u'False') and (str(profile_dump) is u'False') and (str(profile_commands) is u'False'):
            kwargs.pop('section_name')
            kwargs.pop('bear_name')
            kwargs.pop('profile_output')
            kwargs.pop('profile_dump')
            kwargs.pop('profile_commands')
            return False, args, kwargs
        if str(profile_dump) is not u'False' :
            kwargs.pop('profile_dump')
            kwargs.pop('profile_output')
            kwargs.pop('profile_commands')
            path =  os.getcwd()
            if str(profile_dump)==u'True':
                filename = '{}_{}.prof'.format(
                    kwargs['section_name'], kwargs['bear_name'])
                open(filename, 'w+')
                kwargs.pop('section_name')
                kwargs.pop('bear_name')
                cProfile.runctx('self.run(*args, **kwargs)',
                                globals(), locals(), filename)
            else:
                subdir = str(profile_dump)
                filepath = os.path.join(path, subdir)
                if os.path.isdir(filepath):
                    os.chdir(subdir)
                else:
                    os.mkdir(os.path.join(path, subdir))
                    os.chdir(subdir)
                filename = '{}_{}.prof'.format(
                    kwargs['section_name'], kwargs['bear_name'])
                open(filename, 'w+')
                kwargs.pop('section_name')
                kwargs.pop('bear_name')
                cProfile.runctx('self.run(*args, **kwargs)',
                                globals(), locals(), filename)
                os.chdir("..")
            return False, args, kwargs
        if str(profile_output) is not u'False':
            str_profile_bears = str(profile_bears[0]).lower().strip()
            prof = cProfile.Profile()
            kwargs.pop('section_name')
            kwargs.pop('bear_name')
            kwargs.pop('profile_dump')
            kwargs.pop('profile_commands')
            if not str_profile_bears == u'false':
                if (u'wrapping_function of' in str(self.run)) or (u'_new_func of' in str(self.run)):
                    kwargs['profiler'] = prof
                else:
                    kwargs.pop('profile_output')
                    prof.enable()
                retval = self.run(*args, **kwargs)
                if inspect.isgenerator(retval):
                    retval, retval_clone = itertools.tee(retval)
                    for i in retval_clone:
                        pass
                prof.disable()
                check_trim = True if 'no_trim' in profile_bears else False
                if str_profile_bears == u'true':
                    self.setup_profiler_table(prof, profile_bears, check_trim)
                else:
                    try:
                        with open(str_profile_bears, 'a') as stream:
                            ps = self.pstats_config(prof, stream, profile_bears)
                            if check_trim:
                                ps.print_stats()
                            else:
                                ps.print_stats()
                            stream.close()
                    except FileNotFoundError:
                        self.err('No such file or directory: "{}", '
                                 'the first argument to `--profile-bears`'
                                 ' must be true or a valid file path'.format(
                                     str_profile_bears))
                return retval, args, kwargs
            else:
                kwargs.pop('profile_output')
                return False, args, kwargs
        if str(profile_commands) is not u'False':
            print(profile_bears)
            str_profile_bears = str(profile_bears[0]).lower().strip()
            prof = cProfile.Profile()
            kwargs.pop('section_name')
            kwargs.pop('bear_name')
            kwargs.pop('profile_dump')
            kwargs.pop('profile_output')
            if str_profile_bears is not None:
                if (u'wrapping_function of' in str(self.run)) or (u'_new_func of' in str(self.run)):
                    kwargs['profiler'] = prof
                else:
                    kwargs.pop('profile_commands')
                    prof.enable()
                retval = self.run(*args, **kwargs)
                if inspect.isgenerator(retval):
                    retval, retval_clone = itertools.tee(retval)
                    for i in retval_clone:
                        pass
                prof.disable()
                check_trim = True if 'no_trim' in profile_bears else False
                self.setup_profiler_table(prof, profile_bears, check_trim)
                return retval, args, kwargs
            else:
                kwargs.pop('profile_commands')
                return False, args, kwargs

    def run_bear_from_section(self, args, kwargs):
        try:
            # Don't get `language` setting from `section.contents`
            if self.section.language and (
                    'language' in self.get_metadata()._optional_params or
                    'language' in self.get_metadata()._non_optional_params):
                kwargs['language'] = self.section.language
            kwargs.update(
                self.get_metadata().create_params_from_section(self.section))
        except ValueError as err:
            self.warn('The bear {} cannot be executed.'.format(
                self.name), str(err))
            return

        profile_bears_results, args, kwargs = self.setup_profiler(
            *args, **kwargs)

        # ForkedPdb().set_trace()
        return profile_bears_results if profile_bears_results else self.run(
            *args, **kwargs)

    def execute(self, *args, debug=False, **kwargs):
        name = self.name
        try:
            self.debug('Running bear {}...'.format(name))

            # If `dependency_results` kwargs is defined but there are no
            # dependency results (usually in Bear that has no dependency)
            # delete the `dependency_results` kwargs, since most Bears don't
            # define `dependency_results` kwargs in its `run()` function.
            if ('dependency_results' in kwargs and
                    kwargs['dependency_results'] is None and
                    not self.BEAR_DEPS):
                del kwargs['dependency_results']

            # If it's already a list it won't change it
            result = self.run_bear_from_section(args, kwargs)
            return [] if result is None else list(result)
        except (Exception, SystemExit) as exc:
            if debug and not isinstance(exc, SystemExit):
                raise

            if isinstance(exc, ZeroOffsetError):
                self.err('Bear {} violated one-based offset convention.'
                         .format(name), str(exc))

            if self.kind() == BEAR_KIND.LOCAL:
                self.err('Bear {} failed to run on file {}. Take a look '
                         'at debug messages (`-V`) for further '
                         'information.'.format(name, args[0]))
            else:
                self.err('Bear {} failed to run. Take a look '
                         'at debug messages (`-V`) for further '
                         'information.'.format(name))
            self.debug(
                'The bear {bear} raised an exception. If you are the author '
                'of this bear, please make sure to catch all exceptions. If '
                'not and this error annoys you, you might want to get in '
                'contact with the author of this bear.\n\nTraceback '
                'information is provided below:\n\n{traceback}'
                '\n'.format(bear=name, traceback=traceback.format_exc()))

    @staticmethod
    def kind():
        """
        :return: The kind of the bear
        """
        raise NotImplementedError

    @classmethod
    def get_metadata(cls):
        """
        :return: Metadata for the run function. However parameters like
                 ``self`` or parameters implicitly used by coala (e.g.
                 filename for local bears) are already removed.
        """
        return FunctionMetadata.from_function(
            cls.run,
            omit={'self', 'dependency_results', 'language'})

    @classmethod
    def __json__(cls):
        """
        Override JSON export of ``Bear`` object.
        """
        # json cannot serialize properties, so drop them
        _dict = {key: value for key, value in get_public_members(cls).items()
                 if not isinstance(value, property)}
        metadata = cls.get_metadata()
        non_optional_params = metadata.non_optional_params
        optional_params = metadata.optional_params
        _dict['metadata'] = {
            'desc': metadata.desc,
            'non_optional_params': ({param: non_optional_params[param][0]}
                                    for param in non_optional_params),
            'optional_params': ({param: optional_params[param][0]}
                                for param in optional_params)}
        if hasattr(cls, 'languages'):
            _dict['languages'] = (str(language) for language in cls.languages)
        return _dict

    @classmethod
    def missing_dependencies(cls, lst):
        """
        Checks if the given list contains all dependencies.

        :param lst: A list of all already resolved bear classes (not
                    instances).
        :return:    A set of missing dependencies.
        """
        return set(cls.BEAR_DEPS) - set(lst)

    @classmethod
    def get_non_optional_settings(cls, recurse=True):
        """
        This method has to determine which settings are needed by this bear.
        The user will be prompted for needed settings that are not available
        in the settings file so don't include settings where a default value
        would do.

        Note: This function also queries settings from bear dependencies in
        recursive manner. Though circular dependency chains are a challenge to
        achieve, this function would never return on them!

        :param recurse: Get the settings recursively from its dependencies.
        :return:        A dictionary of needed settings as keys and a tuple of
                        help text and annotation as values.
        """
        non_optional_settings = {}

        if recurse:
            for dependency in cls.BEAR_DEPS:
                non_optional_settings.update(
                    dependency.get_non_optional_settings())

        non_optional_settings.update(cls.get_metadata().non_optional_params)

        return non_optional_settings

    @staticmethod
    def setup_dependencies():
        """
        This is a user defined function that can download and set up
        dependencies (via download_cached_file or arbitrary other means) in an
        OS independent way.
        """

    @classmethod
    def check_prerequisites(cls):
        """
        Checks whether needed runtime prerequisites of the bear are satisfied.

        This function gets executed at construction.

        Section value requirements shall be checked inside the ``run`` method.
        >>> from dependency_management.requirements.PipRequirement import (
        ... PipRequirement)
        >>> class SomeBear(Bear):
        ...     REQUIREMENTS = {PipRequirement('pip')}

        >>> SomeBear.check_prerequisites()
        True

        >>> class SomeOtherBear(Bear):
        ...     REQUIREMENTS = {PipRequirement('really_bad_package')}

        >>> SomeOtherBear.check_prerequisites()
        'really_bad_package is not installed. You can install it using ...'

        >>> class anotherBear(Bear):
        ...     REQUIREMENTS = {PipRequirement('bad_package', '0.0.1')}

        >>> anotherBear.check_prerequisites()
        'bad_package 0.0.1 is not installed. You can install it using ...'

        :return: True if prerequisites are satisfied, else False or a string
                 that serves a more detailed description of what's missing.
        """
        for requirement in cls.REQUIREMENTS:
            if not requirement.is_installed():
                return str(requirement) + ' is not installed. You can ' + (
                    'install it using ') + (
                    ' '.join(requirement.install_command()))
        return True

    def get_config_dir(self):
        """
        Gives the directory where the configuration file is.

        :return: Directory of the config file.
        """
        return get_config_directory(self.section)

    def download_cached_file(self, url, filename):
        """
        Downloads the file if needed and caches it for the next time. If a
        download happens, the user will be informed.

        Take a sane simple bear:

        >>> from queue import Queue
        >>> bear = Bear(Section("a section"), Queue())

        We can now carelessly query for a neat file that doesn't exist yet:

        >>> from os import remove
        >>> if exists(join(bear.data_dir, "a_file")):
        ...     remove(join(bear.data_dir, "a_file"))
        >>> file = bear.download_cached_file("https://github.com/", "a_file")

        If we download it again, it'll be much faster as no download occurs:

        >>> newfile = bear.download_cached_file("https://github.com/", "a_file")
        >>> newfile == file
        True

        :param url:      The URL to download the file from.
        :param filename: The filename it should get, e.g. "test.txt".
        :return:         A full path to the file ready for you to use!
        """
        filename = join(self.data_dir, filename)
        if exists(filename):
            return filename

        self.info('Downloading {filename!r} for bear {bearname} from {url}.'
                  .format(filename=filename, bearname=self.name, url=url))

        response = requests.get(url, stream=True, timeout=20)
        response.raise_for_status()

        with open(filename, 'wb') as file:
            for chunk in response.iter_content(chunk_size=16 * 1024):
                file.write(chunk)
        return filename

    @classproperty
    def data_dir(cls):
        """
        Returns a directory that may be used by the bear to store stuff. Every
        bear has an own directory dependent on their name.
        """
        data_dir = abspath(join(user_data_dir('coala-bears'), cls.name))

        makedirs(data_dir, exist_ok=True)
        return data_dir

    @property
    def new_result(self):
        """
        Returns a partial for creating a result with this bear already bound.
        """
        return partial(Result.from_values, self)
