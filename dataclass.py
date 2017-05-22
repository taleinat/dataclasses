# TODO:

#  what exception to raise when non-default follows default? currently
#  ValueError

#  what to do if a user specifies a function we're going to overwrite,
#  like __init__? error? overwrite it?

#  use typing.get_type_hints() instead of accessing __annotations__
#  directly? recommended by PEP 526, but that's importing a lot just
#  to get at __annotations__

# if needed for efficiency, compute self_tuple and other_tuple just once, and pass them around

import collections

__all__ = ['dataclass', 'field']

_MISSING = "MISSING"
_MARKER = '__marker__'
_SELF_NAME = '_self'
_OTHER_NAME = '_other'


class field:
    def __init__(self, *, default=_MISSING):
        self.default = default


def _to_field_definition(type):
    return type


def _tuple_str(obj_name, fields):
    # Special case for the 0-tuple
    if len(fields) == 0:
        return '()'
    # Note the trailing comma, needed for 1-tuple
    return f'({",".join([f"{obj_name}.{f}" for f in fields])},)'


def _create_fn(name, args, body, locals=None):
    # Note that we mutate locals. Caller beware!
    if locals is None:
        locals = {}
    args = ','.join(args)
    body = '\n'.join(f' {b}' for b in body)
    txt = f'def {name}({args}):\n{body}'
    #print(txt)
    exec(txt, None, locals)
    return locals[name]


def _create_init(fields):
    args = [_SELF_NAME] + [(f if info.default is _MISSING else f"{f}=_def_{f}") for f, info in fields.items()]
    body_lines = [f'{_SELF_NAME}.{f}={f}' for f in fields]
    if len(body_lines) == 0:
        body_lines = ['pass']

    # Locals contains defaults, supply them.
    locals = {f'_def_{f}': info.default
              for f, info in fields.items() if info.default is not _MISSING}
    return _create_fn('__init__',
                      args,
                      body_lines,
                      locals)


def _create_repr(fields):
    return _create_fn('__repr__',
                      [f'{_SELF_NAME}'],
                      [f'return {_SELF_NAME}.__class__.__name__ + f"(' + ','.join([f"{k}={{{_SELF_NAME}.{k}!r}}" for k in fields]) + ')"'],
                      )


def _create_cmp_fn(name, op, fields):
    self_tuple = _tuple_str(_SELF_NAME, fields)
    other_tuple = _tuple_str(_OTHER_NAME, fields)
    return _create_fn(name,
                      [_SELF_NAME, _OTHER_NAME],
                      [f'if {_OTHER_NAME}.__class__ is '
                          f'{_SELF_NAME}.__class__:',
                       f'    return {self_tuple}{op}{other_tuple}',
                        'return NotImplemented'],
                      )


def _create_eq(fields):
    return _create_cmp_fn('__eq__', '==', fields)


def _create_ne(fields):
    # __ne__ is slightly different, use a different pattern.
    return _create_fn('__ne__',
                      [_SELF_NAME, _OTHER_NAME],
                      [f'result = {_SELF_NAME}.__eq__({_OTHER_NAME})',
                        'return NotImplemented if result is NotImplemented '
                            'else not result',
                       ],
                      )


def _create_lt(fields):
    return _create_cmp_fn('__lt__', '<',  fields)


def _create_le(fields):
    return _create_cmp_fn('__le__', '<=', fields)


def _create_gt(fields):
    return _create_cmp_fn('__gt__', '>',  fields)


def _create_ge(fields):
    return _create_cmp_fn('__ge__', '>=', fields)


def _create_hash(fields):
    self_tuple = _tuple_str(_SELF_NAME, fields)
    return _create_fn('__hash__',
                      [_SELF_NAME],
                      [f'return hash({self_tuple})'])


def _find_fields(cls):
    # Return a list tuples of tuples of (name, field), in order,
    #  for this class (and no subclasses).  Fields are found from
    #  __annotations__.  Default values are class attributes, if a
    #  field has a default.

    annotations = getattr(cls, '__annotations__', {})

    results = []
    for name, type in annotations.items():
        # If the default value isn't derived from field, then it's
        # only a normal default value.  Convert it to a field().
        default = getattr(cls, name, _MISSING)
        if not isinstance(default, field):
            default = field(default=default)
        results.append((name, default))
    return results


def dataclass(cls):
    fields = collections.OrderedDict()

    # In reversed order so that most derived class overrides earlier
    #  definitions.
    for m in reversed(cls.__mro__):
        # Only process classes marked with our decorator, or our own
        #  class.  Special case for ourselves because we haven't added
        #  _MARKER to ourselves yet.
        if m is cls or hasattr(m, _MARKER):
            for name, fieldinfo in _find_fields(m):
                fields[name] = fieldinfo

                if m is cls:
                    # If the class attribute exists and is of type
                    # 'field', replace it with the real default.  This
                    # is so that normal class introspection sees a
                    # real default value.
                    if isinstance(getattr(cls, name, None), field):
                        setattr(cls, name, fieldinfo.default)

    setattr(cls, _MARKER, True)

    # Make sure we don't have fields without defaults following fields
    #  with defaults.  If I switch to building the source to the
    #  __init__ function and compiling it, this isn't needed, since it
    #  will catch the problem.
    seen_default = False
    for k, v in fields.items():
        if v.default is not _MISSING:
            seen_default = True
        else:
            if seen_default:
                raise ValueError(f'non-default argument {k} follows default argument')

    # Create __init__.
    cls.__init__ = _create_init(fields)

    # Create __repr__.
    cls.__repr__ = _create_repr(fields)

    # Create comparison functions.
    cls.__eq__ = _create_eq(fields)
    cls.__ne__ = _create_ne(fields)
    cls.__lt__ = _create_lt(fields)
    cls.__le__ = _create_le(fields)
    cls.__gt__ = _create_gt(fields)
    cls.__ge__ = _create_ge(fields)

    cls.__hash__ = _create_hash(fields)

    return cls