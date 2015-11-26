import re
import os
import hashlib
import glob
import megazord

class Target:
    def __init__(self, sources, output=None, compiler=None, entry_point=None, delayed=True, name=None, forced=False):
        # Parse sources
        self.delayed = delayed
        self.forced = forced
        self.sources_arg = sources
        self.output_arg = output
        self.compiler_arg = compiler
        self.sources_names = None
        self.sources_formats = None
        self.language = 'unknown'
        self.compiled = False
        self.set_name(name)
        self.set_output(self.output_arg)

        if not self.delayed:
            self.set_sources(self.sources_arg)
            self.__detect_language()
            self.set_compiler(self.compiler_arg)

        self.set_entry_point(entry_point)
        self.optimization_level = 0
        self.libraries = []
        self.includies = []
        self.library_paths = []
        self.include_paths = []
        self.options = []
        self.dependencies = []

    def add_include(self, names):
        if isinstance(names, list):
            self.includies.extend(names)
        else:
            self.includies.append(names)
        return self

    def add_include_path(self, paths):
        if isinstance(paths, list):
            self.include_paths.extend(paths)
        else:
            self.include_paths.append(paths)
        return self

    def add_library(self, names):
        if isinstance(names, list):
            self.libraries.extend(names)
        else:
            self.libraries.append(names)
        return self

    def add_library_path(self, paths):
        if isinstance(paths, list):
            self.library_paths.extend(paths)
        else:
            self.library_paths.append(paths)
        return self

    def add_options(self, options):
        if isinstance(options, list):
            self.options.extend(options)
        else:
            self.options.append(options)
        return self

    def add_support(self, objs):
        if not isinstance(objs, list):
            objs = [objs]
        for obj in objs:
            self.add_include_path(megazord.meta.include_paths(obj))\
                .add_library_path(megazord.meta.library_paths(obj))\
                .add_library(megazord.meta.library(obj))
        return self

    def assembly(self, forced=None):
        if forced is None:
            forced = self.forced
        for dependency in self.dependencies:
            if forced == 'cascade':
                dependency.assembly(forced='cascade')
            else:
                dependency.assembly()
        if self.delayed:
            self.set_sources(self.sources_arg)
            self.__detect_language()
            self.set_compiler(self.compiler_arg)
        new_hash = self.hash()
        old_hash = megazord.interstate.target_storage[self.name]['hash']
        if megazord.system.exists(self.output_dir + self.output) and new_hash == old_hash and not (forced or forced == 'cascade'):
            megazord.system.info("Target {} loaded from cache".format(self.name))
        else:
            self.compiler.compile(self)
            megazord.interstate.target_storage[self.name]['hash'] = new_hash
        self.compiled = True
        return self

    def depends_on(self, args):
        if isinstance(args, list):
            self.dependencies.extend(args)
        else:
            self.dependencies.append(args)
        return self

    def deploy_to(self, path, with_dependencies = True, exclude = None):
        if not self.compiled:
            raise LookupError('Not compiled yet!')
        if with_dependencies:
            if not isinstance(exclude, list):
                exclude = [exclude]
            for dependency in self.dependencies:
                if dependency not in exclude:
                    dependency.deploy_to(path, exclude = exclude)
        megazord.system.copy(self.output_dir + self.output, path)

    def __detect_language(self):
        self.language = megazord.meta.get_language_by(self.sources_formats)
        if len(self.language) > 1:
            raise ValueError("Multiple languages detected in {}".format(self.sources))
        else:
            self.language = self.language[0]

    def hash(self):
        all_hashes = []
        for dependency in self.dependencies:
            all_hashes.append(dependency.hash())
        all_hashes.extend(self.includies)
        all_hashes.extend(self.include_paths)
        all_hashes.extend(self.libraries)
        all_hashes.extend(self.library_paths)
        all_hashes.append(str(self.optimization_level))
        all_hashes.append(str(self.entry_point))
        for source in self.sources:
            all_hashes.append(megazord.utils.filehash(source, hashlib.md5))
        return megazord.utils.reduce_hash(sorted(all_hashes), hashlib.md5)

    def get_sources(self):
        return self.sources

    def set_entry_point(self, entry_point):
        self.entry_point = entry_point
        return self

    def set_compiler(self, compiler):
        self.compiler = compiler
        if isinstance(self.compiler, megazord.GenericCompiler):
            pass
        elif isinstance(self.compiler, str):
            self.compiler = megazord.meta.get_tool_by_name(self.compiler)
            if self.compiler is None:
                raise FileNotFoundError("{} was not found.".format(compiler))
        elif self.compiler is None:
            self.compiler = megazord.meta.get_tool_by_language(self.language)
            if self.compiler is None:
                raise FileNotFoundError("No compiler for {} was found.".format(self.language))
        megazord.system.info("{} used for the target {}".format(self.compiler.path, self.name))
        return self

    def set_name(self, name):
        if name is None:
            h = hashlib.md5()
            h.update(self.output_arg.encode('utf-8'))
            self.name = h.hexdigest()
        else:
            self.name = name
        return self

    def set_optimization_level(self, optimization_level):
        self.optimization_level = optimization_level
        return self

    def set_output(self, output):
        self.output = output
        if self.output is None:
            self.output = self.name + megazord.meta.get_default_output_format_for_language(self.language)
            self.output_dir = ''
        elif self.output.endswith('/'):
            self.output_dir = self.output
            self.output = self.name  + megazord.meta.get_default_output_format_for_language(self.language)
        else:
            self.output_dir = os.path.dirname(os.path.relpath(self.output))
            self.output = os.path.basename(self.output)

        if len(self.output_dir) == 0:
            self.output_dir = '.'
        if not self.output_dir.endswith('/'):
            self.output_dir += '/'

        megazord.system.mkdir_p(self.output_dir)
        self.output_name, self.output_format = os.path.splitext(self.output)
        return self

    def set_output_dir(self, dir):
        self.output_dir = dir
        megazord.system.mkdir_p(dir)
        return self

    def set_sources(self, sources):
        self.sources = []
        if isinstance(sources, str):
            sources = [sources]
        for files in sources:
            self.sources.extend(glob.glob(files))
        self.sources_names, self.sources_formats = list(map(list, zip(*[os.path.splitext(s) for s in self.sources])))
        return self

