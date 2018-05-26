
from functools import wraps

from .taste import Taste
from .meta import aspectclass
from coalib.settings.FunctionMetadata import FunctionMetadata
import pdb
dbg = pdb.Pdb()

def map_setting_to_aspect(**aspectable_setting):
    """
    Map function arguments with aspect and override it if appropriate.

    This decorator can be used by ``Bear.run()`` to automatically map and
    override bear's setting value with their equivalent aspect or taste.

    The order of setting override from the lowest to highest is:
    - Setting default (in bear's run argument)
    - Aspect/taste default (if aspect is activated in Section)
    - Explicit aspect/taste default (if aspect is activated in Section)
    - Explicit setting

    :param aspectable_setting:
        A dictionary of settings as keys and their equivalent aspect or taste
        as value.
    """
    def _func_decorator(func):

        def _new_func(self, *args, **kwargs):
            if self.section.aspects:
                aspects = self.section.aspects
                for arg, aspect_value in aspectable_setting.items():
                    # Explicit setting takes priority
                    if arg in self.section:
                        continue

                    if isinstance(aspect_value, aspectclass):
                        kwargs[arg] = aspects.get(aspect_value) is not None
                    if isinstance(aspect_value, Taste):
                        aspect_instance = aspects.get(aspect_value.aspect_name)
                        if aspect_instance:
                            kwargs[arg] = aspect_instance.tastes[
                                aspect_value.name]

            debug_flag = kwargs.get('debug_flag')
            if debug_flag:
                kwargs.pop('debug_flag')
                dbg.runcall(func,self,*args,**kwargs)
            return func(self, *args, **kwargs)

        # Keep metadata
        _new_func.__metadata__ = FunctionMetadata.from_function(func)

        _new_func.__doc__ = func.__doc__
        # The above line of code is needed, so that docstring of any bear
        # can't lost because of removing the the @warps tool.
        return _new_func

    return _func_decorator
