# Python Deep Knowledge - Interview Theory

> This file contains detailed theory about how Python works "under the hood".
> Use it to prepare for the spoken part of an interview—when you are asked, "Explain how X works in Python."
> Topics are added gradually as we cover each area.
> Each topic ends with possible interview questions and expected answers.

---

## Contents

1. [Python memory model](#1-python-memory-model)
2. [Mutable vs Immutable](#2-mutable-vs-immutable)
3. [Integer caching / interning](#3-integer-caching--interning)
4. [String interning](#4-string-interning)
5. [GIL - Global Interpreter Lock](#5-gil---global-interpreter-lock)
6. [Garbage Collector](#6-garbage-collector)
7. [Python Data Model](#7-python-data-model-dunder-methods-and-protocols)
8. [Dict internals](#8-dict-internals-hash-table)
9. [List internals](#9-list-internals-dynamic-array)
10. [Generators vs Iterators](#10-generators-vs-iterators)
11. [Decorators under the hood](#11-decorators-under-the-hood)
12. [Context managers under the hood](#12-context-managers-under-the-hood)
13. [Asyncio event loop](#13-asyncio-event-loop)
14. [Threading vs Multiprocessing vs Asyncio](#14-threading-vs-multiprocessing-vs-asyncio)
15. [LEGB scope](#15-legb-scope)
16. [Metaclasses](#16-metaclasses)
17. [Descriptors](#17-descriptors)
18. [Import system](#18-import-system)
19. [__slots__](#19-__slots__)
20. [What's new in Python 3.10+](#20-whats-new-in-python-310)

---

## 1. Python Memory Model

### Key idea: "Everything is an object"

In Python, **every value** is an object that lives on the **heap** (the part of memory managed by the Python runtime). This includes:
- Numbers (`42`, `3.14`)
- Strings (`"hello"`)
- Lists, dictionaries, sets
- Functions, classes, modules
- Even `None`, `True`, and `False`

There are no "primitive types" as in Java or C. When you write `x = 42`, you **do not store the number 42 inside variable x**. Instead:

1. Python creates an **object** of type `int` with the value `42` on the heap
2. Variable `x` becomes a **reference** (pointer) to that object

```python
x = 42
```

What happened in memory:

```
Variable           Heap (memory)
+---+              +------------------+
| x | -----------> | int object       |
+---+              | value: 42        |
                   | refcount: 1      |
                   | type: <class int> |
                   +------------------+
```

### Variables are LABELS, not BOXES

This is the most important shift in thinking. In languages such as C:
- A variable **is** a memory location (a box holding a value)

In Python:
- A variable is a **name (label) attached to an object**
- The same object can have several labels

```python
a = [1, 2, 3]
b = a
```

```
Variables          Heap
+---+
| a | ----+
+---+     |     +------------------+
          +---> | list object      |
+---+     |     | [1, 2, 3]        |
| b | ----+     | refcount: 2      |
+---+           +------------------+
```

`a` and `b` point to the **same object**. Nothing is copied! That is why:

```python
a = [1, 2, 3]
b = a
b.append(4)
print(a)  # [1, 2, 3, 4] - a has changed too!
```

### id() - an object's memory address

Every object has a unique identity (ID), which is its memory address in the CPython implementation:

```python
x = [1, 2, 3]
y = x
z = [1, 2, 3]

print(id(x))  # e.g. 140234866534400
print(id(y))  # same number - same object!
print(id(z))  # different number - new object with the same contents
```

### `is` vs `==`

This follows directly from the memory model:

- `==` compares **values** (whether objects have the same contents)
- `is` compares **identities** (whether they are the same object in memory, i.e. have the same `id()`)

```python
a = [1, 2, 3]
b = [1, 2, 3]
c = a

a == b  # True  - same contents
a is b  # False - different objects in memory
a is c  # True  - same object
```

**Interview rule:** Use `is` ONLY for comparison with `None`, `True`, and `False`:

```python
if x is None:      # CORRECT
if x == None:      # WORKS, but is poor style
if x is not None:  # CORRECT
```

### Every object has 3 things

Every Python object on the heap contains:

1. **Type** - the object's type (`int`, `str`, `list`, ...)
2. **Value** - its actual value/contents
3. **Reference count** - how many variables/structures point to it

```python
import sys

x = "hello"
print(type(x))          # <class 'str'>
print(sys.getrefcount(x))  # 2 (x + temporary reference from getrefcount)
```

### What happens during assignment

```python
x = 10
x = 20
```

This **does NOT change** the object `10`. Here is what happens:

1. Step 1: `int(10)` is created; `x` points to it
2. Step 2: `int(20)` is created; `x` is "detached" from `10` and attached to `20`
3. Object `10` now has a reference count of 0 → ready for deletion (garbage collection)

```
Step 1:                     Step 2:
x ---> int(10)              x ---> int(20)
                            int(10) [refcount: 0, will be deleted]
```

### Passing arguments to functions: "Pass by Object Reference"

Python uses neither "pass by value" nor "pass by reference" in the traditional sense. It uses **pass by object reference** (sometimes called "pass by assignment"):

- The function receives a **copy of the reference** (pointer), not a copy of the object
- If the object is **mutable** (list, dict), the function CAN change it
- If the object is **immutable** (int, str, tuple), the function CANNOT change it

```python
def modify_list(lst):
    lst.append(4)       # Changes the ORIGINAL object
    
def modify_int(n):
    n = n + 1           # Creates a NEW object; the local reference changes
    
my_list = [1, 2, 3]
modify_list(my_list)
print(my_list)          # [1, 2, 3, 4] - original list changed!

my_num = 10
modify_int(my_num)
print(my_num)           # 10 - original int has NOT changed
```

Why? Because `lst.append(4)` **mutates the existing object**, while `n = n + 1` creates a **new int object**, and the local variable `n` now points to it.

### Rebinding vs Mutating

This is the key distinction:

**Rebinding** = the variable now points to a different object:

```python
x = [1, 2, 3]
x = [4, 5, 6]    # rebinding - x points to a NEW object
```

**Mutating** = changing the object itself, which the variable points to:

```python
x = [1, 2, 3]
x.append(4)       # mutating - changing the SAME object
x[0] = 99         # mutating
```

Immutable objects cannot be mutated; only rebinding is possible:

```python
s = "hello"
s[0] = "H"        # TypeError! Strings are immutable
s = "Hello"       # rebinding - OK, a new object
```

### Shallow vs Deep Copy

Because variables hold references, copying requires care:

```python
import copy

original = [[1, 2], [3, 4]]

# Assignment - NO copying
ref = original                  # same object

# Shallow copy - copies the outer list, but inner lists remain the SAME references
shallow = copy.copy(original)   # or original[:] or list(original)
shallow[0].append(99)
print(original)                 # [[1, 2, 99], [3, 4]] - inner list changed!

# Deep copy - copies EVERYTHING recursively
deep = copy.deepcopy(original)
deep[0].append(888)
print(original)                 # [[1, 2, 99], [3, 4]] - original unchanged
```

```
Shallow copy:
original[0] ----+
                 +---> [1, 2]      (SAME object)
shallow[0]  ----+

Deep copy:
original[0] --------> [1, 2]      (different objects,
deep[0]     --------> [1, 2]       same contents)
```

### PyObject struct (CPython internals)

For those who want to go deeper—in the CPython implementation (standard Python), every object is a C `PyObject` structure:

```c
typedef struct {
    Py_ssize_t ob_refcnt;    // reference count
    PyTypeObject *ob_type;    // pointer to the type
} PyObject;
```

All "larger" objects (int, list, etc.) extend this structure with additional fields. For example, `PyLongObject` (int in Python 3) adds fields for storing the number.

This means that even `int(42)` takes up **28 bytes** of memory (on a 64-bit system), unlike C, where an `int` takes 4 bytes:

```python
import sys
print(sys.getsizeof(0))     # 28 bytes
print(sys.getsizeof(42))    # 28 bytes
print(sys.getsizeof(2**30)) # 32 bytes (larger int, needs more space)
print(sys.getsizeof(""))    # 49 bytes (empty string!)
print(sys.getsizeof([]))    # 56 bytes (empty list!)
```

---

### Interview questions - Python Memory Model

**Q1: "How does Python store variables in memory?"**

> Expected answer: "Everything in Python is an object. Objects live on the heap, while variables are simply names (references/labels) pointing to those objects. When I write `x = 42`, Python creates an int object on the heap and x becomes a reference to it. Several variables can point to the same object."

**Q2: "What is the difference between `is` and `==`?"**

> Expected answer: "`==` compares the values (contents) of objects, while `is` checks whether two variables point to the same object in memory—whether they have the same `id()`. In practice, I use `is` only for comparisons with `None`, `True`, and `False`."

**Q3: "Is Python pass-by-value or pass-by-reference?"**

> Expected answer: "Neither. Python uses 'pass by object reference': a function receives a copy of a reference to an object, not a copy of the object itself. If the object is mutable (e.g. a list), the function can mutate it and the caller will see the change. If it is immutable (e.g. an int or string), any 'change' inside the function creates a new object and does not affect the original."

**Q4: "What is the difference between shallow and deep copying?"**

> Expected answer: "A shallow copy copies only the outer container; the inner objects are still the same references. If I make a shallow copy of a list of lists, the inner lists share the same objects. A deep copy (`copy.deepcopy`) recursively copies all nested objects, giving me a fully independent copy."

**Q5: "Why does `int(42)` take 28 bytes in Python but only 4 in C?"**

> Expected answer: "Because everything in Python is an object. Every object has overhead: a reference count, a pointer to its type, and additional fields specific to that type. Internally, CPython uses the `PyObject` struct containing `ob_refcnt` and `ob_type`, while `PyLongObject` adds fields to store the number's value."

---

## 2. Mutable vs Immutable

### The basic distinction

Every Python object is either **mutable** (can be changed) or **immutable** (cannot be changed after creation).

| Immutable | Mutable |
|-----------|---------|
| `int` | `list` |
| `float` | `dict` |
| `bool` | `set` |
| `str` | `bytearray` |
| `tuple` | user-defined classes (by default) |
| `frozenset` | |
| `bytes` | |

**Immutable** = once an object is created, its **value cannot change**. Every "change" actually creates a new object.

**Mutable** = the object can be changed **in place**, without creating a new one.

### Immutable objects in practice

```python
# STRING - immutable
s = "hello"
s[0] = "H"          # TypeError: 'str' object does not support item assignment

# But this WORKS - it rebinds rather than mutates:
s = "Hello"          # new object; s points to it

# INT - immutable
x = 5
x += 1               # x now points to a NEW int(6); the old int(5) is left behind
```

When you perform `x += 1` on an int, Python internally:
1. Creates a new `int(6)` object
2. Rebinds `x` to point to it
3. Removes one reference to the old `int(5)`

We can demonstrate this:

```python
x = 5
print(id(x))    # e.g. 140712488579376
x += 1
print(id(x))    # DIFFERENT id - new object!
```

### Mutable objects in practice

```python
# LIST - mutable
lst = [1, 2, 3]
print(id(lst))       # e.g. 140234866534400
lst.append(4)
print(id(lst))       # SAME id - same object, changed in place!
lst[0] = 99
print(id(lst))       # still the same id

# DICT - mutable
d = {"a": 1}
print(id(d))
d["b"] = 2
print(id(d))         # same id
```

### Why are strings immutable?

This is a common interview question. The reasons:

**1. Hashability - strings can be dictionary keys**
Dictionary keys must be hashable, and hashable objects must have a stable hash throughout their lifetime. If a string could change, its hash would change and the dictionary would no longer be able to find it.

```python
d = {"hello": 42}
# To look up "hello" in a dictionary, Python computes hash("hello")
# If someone could change "hello" to "hellx", its hash would change
# and the dictionary would be corrupted
```

**2. String interning and optimization**
Because strings are immutable, Python can safely share the same string object between several variables (interning). More on this in topic 4.

**3. Thread safety**
Immutable objects are inherently thread-safe: there is no risk of a race condition because nobody can change them.

**4. Predictability**
When you pass a string to a function, you know that function cannot change it. This is not true for mutable objects.

### Tuple - immutable, but... not quite

A tuple is immutable: you cannot add or remove elements. **However**, if a tuple contains mutable objects, those objects CAN change:

```python
t = (1, 2, [3, 4])
t[0] = 99         # TypeError - you cannot replace a tuple element
t[2].append(5)    # WORKS! The list inside the tuple is mutable
print(t)          # (1, 2, [3, 4, 5])
```

What is immutable here? The **references** held by the tuple. A tuple always points to the same objects, but if any of those objects is mutable, it can change.

```
Tuple (immutable references):
+---+---+---+
| 0 | 1 | 2 |     <- positions are fixed
+---+---+---+
  |   |   |
  v   v   v
 int int list [3, 4]  <-- the list CAN change
 (1)  (2)     [3, 4, 5]
```

### Why does this matter for dictionary keys?

A hashable object must have a **constant hash** throughout its lifetime. Immutable objects guarantee this. Therefore:

```python
# Can be a dictionary key:
d = {}
d[42] = "int"           # int - immutable, hashable
d["hello"] = "str"      # str - immutable, hashable
d[(1, 2)] = "tuple"     # tuple - immutable*, hashable

# CANNOT be a dictionary key:
d[[1, 2]] = "list"      # TypeError: unhashable type: 'list'
d[{1, 2}] = "set"       # TypeError: unhashable type: 'set'

# CAUTION: a tuple with a mutable element:
d[(1, [2, 3])] = "x"    # TypeError! This tuple contains a list and is not hashable
```

Rule: A tuple is hashable **only if ALL its elements are hashable**.

### The `+=` operator - a surprise!

`+=` behaves DIFFERENTLY for mutable and immutable types:

```python
# Immutable (int):
x = 5
y = x
x += 1
print(x, y)    # 6, 5 - different objects

# Mutable (list):
a = [1, 2]
b = a
a += [3]
print(a, b)    # [1, 2, 3], [1, 2, 3] - same object!
```

Why? For lists, `+=` calls `__iadd__` (in-place addition), which mutates the object. For ints, `+=` calls `__add__`, which creates a new object.

```python
# For a list: a += [3] is equivalent to a.extend([3]) - mutation
# For an int: x += 1 is equivalent to x = x + 1 - rebinding
```

**But be careful**: `a = a + [3]` creates a NEW list object (unlike `a += [3]`):

```python
a = [1, 2]
b = a
a = a + [3]     # NEW object
print(a, b)     # [1, 2, 3], [1, 2] - different!
```

### Copying mutable objects - summary

Now that you understand mutability, here is the complete overview:

```python
# REFERENCE (copies nothing)
b = a

# SHALLOW COPY (copies the outer container)
b = a[:]              # slice - lists only
b = list(a)           # constructor
b = a.copy()          # method
b = copy.copy(a)      # copy module

# DEEP COPY (copies everything recursively)
b = copy.deepcopy(a)
```

### Mutable default arguments - A CLASSIC PITFALL

This is one of the best-known Python gotchas and is frequently asked about in interviews:

```python
def add_item(item, lst=[]):
    lst.append(item)
    return lst

print(add_item(1))    # [1]
print(add_item(2))    # [1, 2] - NOT [2]!
print(add_item(3))    # [1, 2, 3] - NOT [3]!
```

Why? Default arguments are evaluated **once**, when the function is defined, not when it is called. That empty list is created once and shared across all calls.

**The correct pattern:**

```python
def add_item(item, lst=None):
    if lst is None:
        lst = []
    lst.append(item)
    return lst
```

---

### Interview questions - Mutable vs Immutable

**Q1: "What is the difference between mutable and immutable types in Python?"**

> Expected answer: "Immutable objects (int, str, tuple, frozenset) cannot change after creation; every 'change' actually creates a new object. Mutable objects (list, dict, set) can change in place without creating a new object. This affects assignment and argument passing, and determines whether a type can serve as a dictionary key."

**Q2: "Why are strings immutable in Python?"**

> Expected answer: "Three main reasons: (1) Hashability—strings can be dictionary keys because their hash stays constant. (2) Safe sharing—Python can intern strings and share one object between multiple references without risk. (3) Thread safety—immutable objects are inherently thread-safe because they cannot change."

**Q3: "Is a tuple truly immutable?"**

> Expected answer: "A tuple is immutable in the sense that its references cannot change: you cannot add, remove, or replace an element. However, if an element is a mutable object (e.g. a list), that object can change. That is why a tuple containing mutable elements is not hashable and cannot be a dictionary key."

**Q4: "Explain the problem with mutable default arguments."**

> Expected answer: "Default arguments are evaluated once when the function is defined, not on every call. If the default is a mutable object such as a list, that same list is shared by all calls. The solution is to use `None` as the default and create a new object inside the function: `if lst is None: lst = []`."

**Q5: "How does `+=` differ for a list and an int?"**

> Expected answer: "For an int (immutable), `x += 1` creates a new object; it is equivalent to `x = x + 1`. For a list (mutable), `a += [3]` mutates the existing object by calling `__iadd__`, which works like `extend`. Thus, if two variables point to the same list, both reflect the change from `+=`, whereas this does not happen for an int."

---

## 3. Integer Caching / Interning

### What is integer caching?

CPython (the standard Python implementation) pre-creates and caches integer objects in the range **-5 to 256**. These objects are created once when the interpreter starts and reused whenever you need a number in that range.

This means `a = 42` and `b = 42` point to the **same object in memory**:

```python
a = 42
b = 42
print(a is b)    # True - same object!
print(id(a))     # e.g. 140712488579376
print(id(b))     # same number

a = 300
b = 300
print(a is b)    # False (or True, depending on context - see below)
print(id(a))     # different from id(b)
print(id(b))
```

### Why -5 to 256 specifically?

These are the numbers **most frequently used** in typical programs:
- Loop indices (0, 1, 2, ...)
- Status codes and small constants
- Boolean conversions (0, 1)

Caching these numbers avoids millions of heap allocations during program execution. The CPython team chose the -5 to 256 range empirically.

### How it works internally

When the CPython interpreter starts, it creates an array of 262 `PyLongObject` objects (the `small_ints` array):

```
small_ints[0]   -> int(-5)
small_ints[1]   -> int(-4)
...
small_ints[5]   -> int(0)
small_ints[6]   -> int(1)
...
small_ints[261] -> int(256)
```

When you write `x = 42`, CPython does not create a new object. Instead, it returns a pointer to `small_ints[47]` (because 42 + 5 = 47).

### Caution: `is` with numbers outside the cache

```python
# In an interactive REPL:
a = 257
b = 257
print(a is b)    # False - different objects

# BUT in the same .py file or on the same line:
a = 257; b = 257
print(a is b)    # True! (compiler optimization)
```

Why the difference? The Python compiler can optimize identical literals in the same code block by sharing one constant object. This is a **compiler optimization**, not interning.

**Key takeaway:** NEVER use `is` to compare numbers! Use `==`. The behavior of `is` for numbers outside -5..256 is an **implementation detail** and is not guaranteed.

```python
# WRONG:
if status_code is 200:      # may work, but is a BUG waiting to happen
    print("OK")

# CORRECT:
if status_code == 200:
    print("OK")
```

### `is` vs `==` - a complete behavior comparison

```python
# Small integers (-5 to 256) - cached:
a = 100
b = 100
a == b    # True (same value)
a is b    # True (same cached object)

# Large integers - NOT cached:
a = 1000
b = 1000
a == b    # True (same value)
a is b    # ??? (unpredictable - implementation-dependent)

# Strings - sometimes interned:
a = "hello"
b = "hello"
a == b    # True (same value)
a is b    # True (interned - see topic 4)

a = "hello world!"
b = "hello world!"
a == b    # True
a is b    # ??? (unpredictable)

# None - always one object (singleton):
a = None
b = None
a is b    # True (ALWAYS - None is a singleton)
```

### `bool` is a subclass of `int`

A lesser-known fact: `True` is effectively `int(1)` and `False` is `int(0)`:

```python
isinstance(True, int)     # True!
True == 1                 # True
False == 0                # True
True + True               # 2
True * 10                 # 10

# But:
True is 1                 # False (different types, different objects)
type(True)                # <class 'bool'>
type(1)                   # <class 'int'>
```

`True` and `False` are also singleton objects: there is always exactly one `True` and exactly one `False` in memory.

### sys.intern() - manual interning

Python allows manual string interning (more in topic 4), but there is no public API for integers. Integer caching is fully automatic and limited to -5..256.

### Practical implications

**1. Memory savings:**

```python
import sys

# 1000 variables with the value 42:
lst = [42] * 1000
# All 1000 elements point to the SAME int(42) object
# Instead of 1000 * 28 bytes = 28KB, only 28 bytes plus a list of references are used
```

**2. Performance:**
Creating a new int object requires allocating heap memory. For cached numbers, Python simply returns an existing pointer, which is much faster.

**3. A debugging pitfall:**

```python
a = 256
b = 256
print(a is b)  # True - because it is cached

a = 257
b = 257
print(a is b)  # False in the REPL, True in a script - confusing!
```

---

### Interview questions - Integer Caching

**Q1: "What is integer caching in Python?"**

> Expected answer: "CPython pre-creates and caches integer objects from -5 to 256. When you use a number in that range, Python returns a reference to the existing cached object instead of creating a new one. That is why `a = 42; b = 42; a is b` returns `True`: both variables point to the same object."

**Q2: "Why should you avoid using `is` to compare numbers?"**

> Expected answer: "Because integer caching covers only -5 to 256 and is a CPython implementation detail, not part of the Python specification. Outside that range, `is` may return True or False depending on the context (REPL vs script, same line vs separate lines). Always use `==` for value comparisons. Use `is` only for `None`, `True`, and `False`."

**Q3: "What is the cached integer range, and why was it chosen?"**

> Expected answer: "-5 to 256. This range was chosen empirically because it covers the most common numbers in typical programs: loop indices, small constants, and status codes. Caching avoids unnecessarily creating millions of short-lived objects on the heap."

---

## 4. String Interning

### What is string interning?

String interning is a technique in which Python stores **one copy** of each identical string and shares it among all references. It is similar to integer caching, but follows different rules.

```python
a = "hello"
b = "hello"
print(a is b)    # True - same object in memory!
```

Python automatically "interned" `"hello"`: because it already exists in memory, `b` receives a reference to that same object rather than a new object being created.

### Which strings are automatically interned?

CPython automatically interns strings that look like **valid identifiers** (variable names):
- They contain only letters, digits, and underscores
- They do not begin with a digit

```python
# Automatically interned (look like identifiers):
a = "hello"
b = "hello"
print(a is b)         # True

a = "hello_world"
b = "hello_world"
print(a is b)         # True

a = "_private"
b = "_private"
print(a is b)         # True

# NOT automatically interned (contain special characters):
a = "hello world"     # space
b = "hello world"
print(a is b)         # False (or True within the same compilation block - optimization)

a = "hello!"          # exclamation mark
b = "hello!"
print(a is b)         # False (or True - depends on context)
```

### Why only identifier-like strings?

Because Python internally uses strings for:
- **Variable names** (`my_var`)
- **Attribute names** (`obj.name`)
- **Method names** (`obj.calculate()`)
- **Dictionary keys** (namespaces are dictionaries!)

These strings are compared millions of times during program execution. Interning enables pointer comparison (O(1)) instead of character-by-character comparison (O(n)):

```python
# Without interning:
"my_variable_name" == "my_variable_name"   # compares 18 characters

# With interning:
id(a) == id(b)                             # compares 2 numbers (pointers)
```

### Compile-time optimizations (constant folding)

The CPython compiler also merges identical string constants within a code block:

```python
# All of this happens at compile time:
a = "hello" + " " + "world"    # compiler combines them into "hello world"
b = "hello world"
print(a is b)                   # True (same constant object)

# But runtime concatenation does NOT intern:
c = "hello"
d = c + " world"
print(d is b)                   # False (d was created at runtime)
```

### sys.intern() - manual interning

If you know you will use the same string many times (e.g. as a dictionary key in a large dataset), you can intern it manually:

```python
import sys

a = sys.intern("hello world!")
b = sys.intern("hello world!")
print(a is b)    # True - now interned

# Practical use - a large dataset with repeated keys:
data = []
for line in huge_file:
    name = sys.intern(line.split(",")[0])   # interns the name
    data.append({"name": name, "value": line.split(",")[1]})
# Instead of a million copies of "John", there is just one
```

### How interning works internally

CPython maintains an internal dictionary (hash table) of all interned strings:

```
intern_table = {
    "hello": <string object "hello" at address 0x7f...>,
    "world": <string object "world" at address 0x7f...>,
    ...
}
```

When you call `sys.intern(s)`:
1. It checks whether `s` already exists in `intern_table`
2. If it does, it returns the existing object
3. Otherwise, it adds `s` to the table and returns it

### String interning + immutability

Interning works **only because strings are immutable**. If someone could change an interned string, all variables sharing that object would be corrupted:

```python
a = "hello"
b = "hello"
# a and b point to the same object
# Imagine strings WERE mutable:
a[0] = "H"         # hypothetical
print(b)            # "Hello" - b changed too! DISASTER
```

Because strings are immutable, sharing the same object is completely safe.

### Comparison with Java

If you have worked with Java, this will be familiar:
- Java also has a String pool (similar to interning)
- Java's `String.intern()` = Python's `sys.intern()`
- Java's `==` compares references (like Python's `is`)
- Java's `.equals()` compares contents (like Python's `==`)

Python is safer in this respect because `==` compares values by default.

### Practical interview tips

1. **Never rely on interning for program logic**—use `==` to compare strings
2. **`sys.intern()` is useful** when you have millions of identical strings (e.g. parsing a CSV with repeated column values)
3. **Interning saves memory and speeds up comparisons**, but adds lookup overhead in the intern table
4. **Identifier-like strings** are automatically interned—this is an optimization, not a guarantee

---

### Interview questions - String Interning

**Q1: "What is string interning in Python?"**

> Expected answer: "String interning stores one copy of an identical string and shares it across all references. CPython automatically interns strings resembling identifiers (letters, digits, underscores). You can also intern strings manually using `sys.intern()`. This saves memory and speeds up comparisons by comparing pointers rather than individual characters."

**Q2: "Why does string interning depend on strings being immutable?"**

> Expected answer: "If strings were mutable and multiple variables shared one object, changing it through one variable would affect all the others—a serious bug. Because strings are immutable, sharing an object is completely safe: nobody can change its contents."

**Q3: "When would you use `sys.intern()` in practice?"**

> Expected answer: "When I have a large dataset with many repeated strings—for example, a million-row CSV whose 'country' column has only 200 distinct values. Interning saves memory: instead of a million copies of 'Serbia', I have one. It also speeds up comparisons by using pointers rather than character-by-character comparison."

---

## 5. GIL - Global Interpreter Lock

### What is the GIL?

The GIL (Global Interpreter Lock) is a **mutex** (mutual exclusion lock) that allows only **one thread** to execute Python bytecode at a time, even on a multiprocessor system.

In other words, if you have 8 CPU cores and 8 Python threads, only one executes Python code at any given moment. The others wait.

```
CPU Core 1: [Thread 1 - executing Python]
CPU Core 2: [Thread 2 - WAITING for the GIL]
CPU Core 3: [Thread 3 - WAITING for the GIL]
CPU Core 4: [Thread 4 - WAITING for the GIL]
                   ^
                   |
              Only one thread
              holds the GIL at a time
```

### Why does the GIL exist?

The GIL exists because of **reference counting** (topic 6). Every Python object has an `ob_refcnt`: the number of references to it. When the count falls to 0, the object is deleted.

The problem: what if two threads change the same object's reference count simultaneously?

```
Thread 1: refcount = obj.refcount    # reads 3
Thread 2: refcount = obj.refcount    # reads 3
Thread 1: obj.refcount = refcount + 1  # writes 4
Thread 2: obj.refcount = refcount - 1  # writes 2 (should have been 3!)
```

This is a classic **race condition**. Without the GIL, you would need a lock around EVERY reference-count update, which would be extremely slow (millions of lock/unlock operations per second).

The GIL offers a simple solution: lock the entire interpreter for one thread, preventing this race condition.

### The GIL is NOT a thread lock for your code

A common misconception: the GIL does not mean you can skip locks for your own data!

```python
import threading

counter = 0

def increment():
    global counter
    for _ in range(1_000_000):
        counter += 1    # NOT atomic! counter += 1 is: load, add, store

threads = [threading.Thread(target=increment) for _ in range(2)]
for t in threads:
    t.start()
for t in threads:
    t.join()

print(counter)  # You expect 2_000_000, but get less! (e.g. 1_432_817)
```

Why? The GIL is released and acquired between bytecode instructions. `counter += 1` consists of **multiple** bytecode instructions (LOAD, ADD, STORE), and the GIL can be released between them.

```python
# counter += 1 compiles to:
LOAD_GLOBAL    counter    # Thread 1 loads 100
                          # GIL switches to Thread 2
LOAD_GLOBAL    counter    # Thread 2 loads 100
LOAD_CONST     1
BINARY_ADD                # Thread 2 calculates 101
STORE_GLOBAL   counter    # Thread 2 writes 101
                          # GIL returns to Thread 1
LOAD_CONST     1
BINARY_ADD                # Thread 1 calculates 101 (using the old 100!)
STORE_GLOBAL   counter    # Thread 1 writes 101 (should have been 102!)
```

### When is the GIL NOT a problem?

The GIL is a problem only for **CPU-bound** tasks. For **I/O-bound** tasks, threading works very well because the GIL is released during I/O operations:

```python
# I/O-BOUND - the GIL is released; threading WORKS well:
# - Network requests (HTTP, API calls)
# - Reading/writing files
# - Database queries
# - sleep()

# CPU-BOUND - the GIL is a bottleneck; threading DOES NOT HELP:
# - Mathematical calculations
# - Processing data in a loop
# - Compression/encryption
# - Parsing large structures
```

When a thread performs I/O (e.g. waiting for a server response), it **releases the GIL**, allowing another thread to run:

```
Thread 1: [Python code] [I/O - releases GIL...waits...] [Python code]
Thread 2: [waits for GIL] [Python code]                [waits for GIL]
Thread 3: [waits for GIL] [waits for GIL]              [Python code]
```

### Solutions for CPU-bound parallelism

**1. `multiprocessing` - separate processes**
Each process has its own Python interpreter and GIL. True parallelism!

```python
from multiprocessing import Pool

def heavy_computation(n):
    return sum(i * i for i in range(n))

with Pool(4) as pool:
    results = pool.map(heavy_computation, [10**7] * 4)
# 4 processes, each with its own GIL, run simultaneously
```

**2. `concurrent.futures.ProcessPoolExecutor`**
A more modern API for the same thing:

```python
from concurrent.futures import ProcessPoolExecutor

with ProcessPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(heavy_computation, 10**7) for _ in range(4)]
    results = [f.result() for f in futures]
```

**3. C extensions that release the GIL**
Libraries such as NumPy, pandas, and scikit-learn internally use C/C++ code that releases the GIL:

```python
import numpy as np
# NumPy operations run in C with the GIL released
# Threading can speed up NumPy operations!
a = np.random.rand(10000, 10000)
result = np.dot(a, a)  # releases the GIL internally
```

### How does the GIL switch between threads?

CPython uses a mechanism to share the GIL fairly:

**Python 3.2+:** `sys.setswitchinterval(interval)` defaults to **5 ms** (0.005 seconds). Every 5 ms, the active thread checks whether another thread is waiting for the GIL. If so, it releases it.

```python
import sys
print(sys.getswitchinterval())  # 0.005 (5ms)
sys.setswitchinterval(0.001)     # changes to 1 ms (more context switching)
```

Before Python 3.2, `sys.checkinterval` counted bytecode instructions (default: 100). This was unfair because different instructions take different amounts of time.

### PEP 703 and a future without the GIL (free-threaded Python)

**Python 3.13 (October 2024)** introduces an experimental **free-threaded mode** (without the GIL):

- Installed as a separate build: `python3.13t` (t = threaded)
- The GIL can optionally be disabled, but remains available for compatibility
- Uses fine-grained locking instead of one global lock
- Per-object reference-count locks instead of the GIL
- Biased reference counting: an optimization for objects used by only one thread

**Python 3.14+** continues improving free-threaded mode, but it will take years to become the default.

```python
# Check whether the GIL is enabled (Python 3.13+):
import sys
print(sys._is_gil_enabled())  # True/False
```

This is **the most significant Python change in the past 30 years** and is often discussed in interviews.

### The GIL and asyncio

Asyncio uses **one thread** with an event loop and cooperative multitasking. The GIL is not a problem because multiple threads are not competing for it:

```python
import asyncio

async def fetch(url):
    # await yields control to the event loop (not the GIL)
    response = await aiohttp.get(url)
    return response

# One thread, no GIL contention
await asyncio.gather(fetch(url1), fetch(url2), fetch(url3))
```

---

### Interview questions - GIL

**Q1: "What is the GIL, and why does it exist?"**

> Expected answer: "The Global Interpreter Lock is a mutex allowing only one thread to execute Python bytecode at a time. It exists because CPython uses reference counting for memory management. Without the GIL, every reference-count update would require a lock, which would be much slower than one global lock."

**Q2: "Does the GIL make threading useless in Python?"**

> Expected answer: "No. The GIL is a problem only for CPU-bound tasks. Threading works very well for I/O-bound tasks (network requests, files, database queries), because the GIL is released during I/O. For CPU-bound parallelism, I use multiprocessing, which starts separate processes with their own GILs."

**Q3: "How would you achieve CPU-bound parallelism in Python?"**

> Expected answer: "Three options: (1) `multiprocessing` or `ProcessPoolExecutor`: separate processes with their own GILs, providing true parallelism. (2) C extensions that release the GIL: NumPy and pandas use C code internally. (3) Since Python 3.13, experimental free-threaded mode without the GIL is available, but is not yet production-ready."

**Q4: "What are free-threaded Python and PEP 703?"**

> Expected answer: "PEP 703 introduces optional free-threaded mode in Python 3.13+, allowing the GIL to be disabled. It replaces one global lock with per-object fine-grained locking and biased reference counting. The goal is true multithreaded parallelism without sacrificing compatibility. It is currently experimental and will need several releases to become stable."

**Q5: "Does the GIL protect your data from race conditions?"**

> Expected answer: "No! The GIL protects Python interpreter internals (reference counts), not user data. Operations such as `counter += 1` are not atomic: they compile to several bytecode instructions, and the GIL can switch between them. Protect user data with `threading.Lock` or similar mechanisms."

---

## 6. Garbage Collector

### Two mechanisms for memory management

Python uses **two** mechanisms to remove objects from memory:

1. **Reference counting** - the primary mechanism (fast, deterministic)
2. **Generational garbage collector** - supplementary (catches reference cycles)

### Mechanism 1: Reference Counting

Each object has an `ob_refcnt` counting references to it. When it drops to **0**, the object is deleted **immediately**.

```python
import sys

a = [1, 2, 3]           # refcount: 1 (only 'a')
b = a                    # refcount: 2 ('a' and 'b')
c = [a, a]               # refcount: 4 ('a', 'b', c[0], c[1])

print(sys.getrefcount(a))  # 5 (4 + 1 temporary reference from getrefcount)

del b                    # refcount: 3
c = None                 # refcount: 1 (c no longer holds references)
del a                    # refcount: 0 -> DELETED IMMEDIATELY
```

**What increases the reference count:**
- Assigning to a variable: `x = obj`
- Adding to a container: `lst.append(obj)`, `d["key"] = obj`
- Passing as a function argument
- Creating an alias: `y = x`

**What decreases the reference count:**
- `del x`
- A variable going out of scope (a function returns)
- Rebinding: `x = other_obj`
- Removing from a container: `lst.remove(obj)`

### Advantages of reference counting

1. **Deterministic** - an object is deleted **immediately** when its count reaches 0 (in CPython)
2. **Fast** - increment/decrement operations are inexpensive
3. **Predictable** - you know exactly when an object will be deleted

```python
# Deterministic deletion - file closes as soon as refcount reaches 0:
def process():
    f = open("data.txt")
    data = f.read()
    # f closes automatically when process() finishes
    # because f goes out of scope, refcount reaches 0, and __del__ is called
    return data
```

**However:** this is a CPython implementation detail! PyPy, Jython, and IronPython do not have deterministic reference counting. Always use the `with` statement for resources:

```python
# CORRECT - works across implementations:
with open("data.txt") as f:
    data = f.read()
# f is guaranteed to be closed here
```

### The problem: reference cycles

Reference counting cannot handle **reference cycles**, where objects point to each other:

```python
a = []
b = []
a.append(b)    # a -> b
b.append(a)    # b -> a (CYCLE!)

del a          # refcount of a: 1 (b[0] still points to it)
del b          # refcount of b: 1 (a[0] still points to it)
# Neither a nor b is deleted! Memory leak!
```

```
Before 'del':
a (refcount: 2) <----> b (refcount: 2)
  variable a             variable b
  b[0]                   a[0]

After 'del a' and 'del b':
[object] (refcount: 1) <----> [object] (refcount: 1)
  (b[0] still points here)       (a[0] still points here)
  
The reference count never reaches 0!
```

### Mechanism 2: Generational Garbage Collector

To handle reference cycles, Python has a **generational GC**:

**3 generations:**

| Generation | Contents | Collection |
|------------|----------|------------|
| Gen 0 | New objects | Most frequent (approximately every 700 allocations) |
| Gen 1 | Survivors of Gen 0 | Less frequent |
| Gen 2 | Survivors of Gen 1 | Least frequent |

**The generational hypothesis:** most objects die young. Temporary variables, intermediate results, etc. are deleted quickly. Objects surviving several collections are likely to live a long time.

```python
import gc

# Thresholds for each generation:
print(gc.get_threshold())  # (700, 10, 10)
# Gen 0: runs after 700 new allocations
# Gen 1: runs after 10 Gen 0 collections
# Gen 2: runs after 10 Gen 1 collections
```

### How the GC detects cycles

The GC uses an algorithm based on **container traversal**:

1. For every object that can contain references (lists, dictionaries, classes...), it tracks all references
2. It builds a graph of objects and their connections
3. It identifies objects reachable ONLY through cycles (nothing "outside" points to them)
4. It deletes those objects

```python
# The GC should find:
#   [list_A] <-> [list_B] (cycle, no external references)
#   
# The GC should NOT delete:
#   x -> [list_C] <-> [list_D] (x points to C from outside)
```

**Important:** the GC does not check immutable objects (int, str, tuples without mutable elements), because they cannot create cycles.

### The `gc` module - controlling the garbage collector

```python
import gc

# Trigger collection manually:
gc.collect()                    # full collection (all generations)
gc.collect(generation=0)        # Gen 0 only

# Statistics:
print(gc.get_stats())
# [{'collections': 85, 'collected': 492, 'uncollectable': 0},
#  {'collections': 7, 'collected': 34, 'uncollectable': 0},
#  {'collections': 1, 'collected': 0, 'uncollectable': 0}]

# Thresholds:
gc.set_threshold(1000, 15, 15)  # change thresholds

# Disable GC (rarely needed):
gc.disable()                    # disable automatic GC
gc.enable()                     # enable it

# Find references to an object (debugging):
x = [1, 2, 3]
print(gc.get_referrers(x))      # everything pointing to x
```

### `__del__` - destructor (finalizer)

An object may define a `__del__` method that runs before deletion:

```python
class Resource:
    def __init__(self, name):
        self.name = name
        print(f"Created: {name}")
    
    def __del__(self):
        print(f"Deleted: {self.name}")

r = Resource("test")    # Created: test
del r                   # Deleted: test (immediately, because refcount = 0)
```

**Problems with `__del__`:**
1. **Its timing is not guaranteed** (except in CPython with reference counting)
2. **Reference cycles involving `__del__`** were a problem before Python 3.4: the GC could not delete cycles containing objects with `__del__`, putting them in `gc.garbage`. Python 3.4 (PEP 442) resolved this.
3. **Never rely on `__del__` to release resources**—use a context manager (`with`)

### `weakref` - weak references

A weak reference points to an object **without increasing its reference count**. Useful for caching, the observer pattern, and avoiding reference cycles:

```python
import weakref

class Data:
    def __init__(self, value):
        self.value = value

obj = Data(42)
weak = weakref.ref(obj)

print(weak())          # <Data object> - object still exists
print(weak().value)    # 42

del obj                # refcount reaches 0; object is deleted
print(weak())          # None - object was deleted
```

**Practical application - caching:**

```python
import weakref

class ImageCache:
    def __init__(self):
        self._cache = weakref.WeakValueDictionary()
    
    def get_image(self, path):
        img = self._cache.get(path)
        if img is None:
            img = load_image(path)  # expensive operation
            self._cache[path] = img
        return img

# When nothing else holds a reference to the image,
# the GC can delete it and the cache is cleaned automatically
```

### Memory profiling - practical tools

```python
import sys
import tracemalloc

# Size of a single object:
print(sys.getsizeof([1, 2, 3]))      # 88 bytes (list)
print(sys.getsizeof({"a": 1}))       # 184 bytes (dict)

# Track allocations:
tracemalloc.start()

# ... your code ...
data = [list(range(1000)) for _ in range(1000)]

snapshot = tracemalloc.take_snapshot()
top = snapshot.statistics('lineno')
for stat in top[:5]:
    print(stat)
# Shows which code lines consume the most memory
```

### Comparison with other languages

| Feature | Python (CPython) | Java | Go |
|---------|------------------|------|----|
| Primary mechanism | Reference counting | Tracing GC | Tracing GC |
| Deterministic deletion | Yes (refcount=0 → immediate) | No | No |
| Reference cycles | Generational GC | Tracing GC | Tracing GC |
| Stop-the-world pauses | Minimal | Yes (improved in newer JVMs) | Very short |
| Manual control | `gc` module | `System.gc()` (only a hint) | `runtime.GC()` |

---

### Interview questions - Garbage Collector

**Q1: "How does Python manage memory?"**

> Expected answer: "Python uses two mechanisms: (1) Reference counting—each object counts its references and is immediately deleted when the count reaches 0. (2) Generational garbage collection—a supplementary mechanism detecting reference cycles that reference counting cannot handle. The GC uses 3 generations: new objects enter Gen 0, which is collected most often; older objects move to Gen 1 and Gen 2, collected less frequently."

**Q2: "What are reference cycles, and why are they a problem?"**

> Expected answer: "Reference cycles arise when two or more objects point to one another in a circle. Reference counting cannot delete them because their counts never reach 0: at least one reference from the cycle always remains. Python therefore has a generational GC to detect and correctly delete such cycles."

**Q3: "What are GC generations, and why do they exist?"**

> Expected answer: "There are three generations: Gen 0 for new objects, Gen 1 and Gen 2 for older ones. This follows the generational hypothesis: most objects die young. Gen 0 is collected most frequently (after roughly 700 allocations), Gen 2 least frequently. Objects surviving collection move to the next generation. This is efficient because long-lived objects need not be checked every time."

**Q4: "What is weakref, and when is it used?"**

> Expected answer: "A weak reference points to an object without increasing its reference count. Once the object is deleted, the weak reference returns None. Uses include caches (WeakValueDictionary), the observer pattern, and avoiding reference cycles. It is suitable when a reference should not prevent an object's deletion."

**Q5: "Why should `__del__` not be used to close resources?"**

> Expected answer: "Its timing is not guaranteed and depends on the implementation. CPython calls it immediately when the reference count reaches 0, but PyPy and other implementations may delay it. For files, connections, and locks, always use a context manager (`with`) to ensure deterministic cleanup."

---

## 7. Python Data Model (Dunder Methods and Protocols)

### What is the Python Data Model?

The Python Data Model is a **framework** defining how Python objects interact with the language. Writing `len(x)` effectively calls `x.__len__()`. Writing `a + b` calls `a.__add__(b)`.

This lets you create **your own classes that behave like built-in types**, supporting `+`, `[]`, `len()`, `for` loops, `with`, and more.

Dunder methods (double underscores, e.g. `__len__`) are hooks called by Python. Rather than calling them directly, use operators and built-in functions.

```python
# You write:             # Python internally calls:
len(obj)                  obj.__len__()
str(obj)                  obj.__str__()
repr(obj)                 obj.__repr__()
obj[key]                  obj.__getitem__(key)
obj[key] = val            obj.__setitem__(key, val)
obj + other               obj.__add__(other)
obj == other              obj.__eq__(other)
for x in obj:             obj.__iter__() → __next__()
with obj:                 obj.__enter__() → __exit__()
obj()                     obj.__call__()
if obj:                   obj.__bool__()
hash(obj)                 obj.__hash__()
```

### Representation: `__repr__` vs `__str__`

```python
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
    
    def __repr__(self):
        return f"Point({self.x}, {self.y})"
    
    def __str__(self):
        return f"({self.x}, {self.y})"

p = Point(3, 4)
print(repr(p))    # Point(3, 4) - for developers, unambiguous
print(str(p))     # (3, 4) - readable for users
print(p)          # (3, 4) - print uses __str__
print([p])        # [Point(3, 4)] - containers use __repr__
```

**Rules:**
- `__repr__` should be **unambiguous**; ideally, `eval(repr(obj))` recreates the object
- `__str__` should be **readable** for the end user
- If you implement only one, choose `__repr__`: Python also uses it as a fallback for `__str__`

### Comparison: `__eq__`, `__lt__`, `__le__`, etc.

```python
from functools import total_ordering

@total_ordering
class Temperature:
    def __init__(self, celsius):
        self.celsius = celsius
    
    def __eq__(self, other):
        if not isinstance(other, Temperature):
            return NotImplemented
        return self.celsius == other.celsius
    
    def __lt__(self, other):
        if not isinstance(other, Temperature):
            return NotImplemented
        return self.celsius < other.celsius
    
    def __repr__(self):
        return f"Temperature({self.celsius})"

t1 = Temperature(20)
t2 = Temperature(30)

t1 == t2    # False  → t1.__eq__(t2)
t1 < t2     # True   → t1.__lt__(t2)
t1 <= t2    # True → @total_ordering generates this from __eq__ and __lt__
t1 > t2     # False  → @total_ordering
t1 >= t2    # False  → @total_ordering
```

**`NotImplemented`** - return this (do not raise it!) when you cannot compare with the given type. Python then tries the other side (`other.__eq__(self)`).

**`@total_ordering`** - a decorator that automatically generates `__le__`, `__gt__`, and `__ge__` when you define `__eq__` and one of `__lt__`/`__le__`/`__gt__`/`__ge__`.

### Hashability: `__hash__`

An object is hashable if it has `__hash__` and `__eq__`. The key rule:

> **If two objects compare equal (`__eq__`), they must have the same hash.**

```python
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y
    
    def __eq__(self, other):
        return isinstance(other, Point) and self.x == other.x and self.y == other.y
    
    def __hash__(self):
        return hash((self.x, self.y))

p1 = Point(1, 2)
p2 = Point(1, 2)

d = {p1: "point"}
print(d[p2])          # "point" - works because p1 == p2 and hash(p1) == hash(p2)
print({p1, p2})       # {Point(1, 2)} - the set detects the duplicate
```

**Important:** if you define `__eq__` without `__hash__`, Python automatically sets `__hash__ = None`, making the object **unhashable** (it cannot be a dictionary key or set member).

### Container protocol: `__getitem__`, `__len__`, `__contains__`

```python
class Deck:
    ranks = "2 3 4 5 6 7 8 9 10 J Q K A".split()
    suits = "♠ ♥ ♦ ♣".split()
    
    def __init__(self):
        self._cards = [(r, s) for s in self.suits for r in self.ranks]
    
    def __len__(self):
        return len(self._cards)
    
    def __getitem__(self, index):
        return self._cards[index]
    
    def __contains__(self, card):
        return card in self._cards

deck = Deck()
print(len(deck))              # 52 → __len__
print(deck[0])                # ('2', '♠') → __getitem__
print(deck[-1])               # ('A', '♣') → __getitem__
print(deck[::13])             # slicing works automatically! → __getitem__
print(("A", "♠") in deck)    # True → __contains__

for card in deck:             # for loops work automatically with __getitem__!
    print(card)

import random
print(random.choice(deck))   # random.choice works because we have __len__ + __getitem__
```

**The magic of `__getitem__`**: implementing it alone gives you:
- Iteration (`for` loops)
- Slicing (`deck[2:5]`)
- The `in` operator (without `__contains__`, Python searches using `__getitem__`)
- `random.choice()`, `reversed()`, etc.

### Iterator protocol: `__iter__` and `__next__`

```python
class Countdown:
    def __init__(self, start):
        self.start = start
    
    def __iter__(self):
        self.current = self.start
        return self
    
    def __next__(self):
        if self.current <= 0:
            raise StopIteration
        val = self.current
        self.current -= 1
        return val

for n in Countdown(5):
    print(n)    # 5, 4, 3, 2, 1
```

**Better practice** - separate the iterable from its iterator:

```python
class Countdown:
    def __init__(self, start):
        self.start = start
    
    def __iter__(self):
        current = self.start
        while current > 0:
            yield current
            current -= 1

c = Countdown(3)
list(c)    # [3, 2, 1]
list(c)    # [3, 2, 1] - can be iterated multiple times!
```

### Callable objects: `__call__`

```python
class Multiplier:
    def __init__(self, factor):
        self.factor = factor
    
    def __call__(self, x):
        return x * self.factor

double = Multiplier(2)
triple = Multiplier(3)

print(double(5))     # 10 → double.__call__(5)
print(triple(5))     # 15

print(callable(double))  # True
```

`__call__` is useful for objects that should behave like functions but maintain state, such as a class-based decorator or a configured strategy.

### Numeric protocol: `__add__`, `__radd__`, `__iadd__`

```python
class Vector:
    def __init__(self, x, y):
        self.x = x
        self.y = y
    
    def __add__(self, other):
        if isinstance(other, Vector):
            return Vector(self.x + other.x, self.y + other.y)
        return NotImplemented
    
    def __radd__(self, other):
        return self.__add__(other)
    
    def __mul__(self, scalar):
        return Vector(self.x * scalar, self.y * scalar)
    
    def __rmul__(self, scalar):
        return self.__mul__(scalar)
    
    def __abs__(self):
        return (self.x ** 2 + self.y ** 2) ** 0.5
    
    def __repr__(self):
        return f"Vector({self.x}, {self.y})"

v1 = Vector(1, 2)
v2 = Vector(3, 4)

v1 + v2           # Vector(4, 6)    → v1.__add__(v2)
v1 * 3            # Vector(3, 6)    → v1.__mul__(3)
3 * v1            # Vector(3, 6)    → v1.__rmul__(3)
abs(v1)           # 2.236...        → v1.__abs__()
```

**`__radd__`** (reflected addition) runs when the left operand cannot perform the addition. For example, in `3 + v1`, int does not understand Vector, so Python tries `v1.__radd__(3)`.

### Context Manager protocol: `__enter__` and `__exit__`

```python
class Timer:
    def __enter__(self):
        import time
        self.start = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        self.elapsed = time.perf_counter() - self.start
        print(f"Elapsed: {self.elapsed:.4f}s")
        return False  # does not suppress exceptions

with Timer() as t:
    sum(range(1_000_000))
# Elapsed: 0.0234s
```

### Boolean conversion: `__bool__` and `__len__`

Python checks truthiness in this order:
1. `__bool__()`, if present
2. `__len__()`, if present (falsy when 0)
3. Always `True`, if neither exists

```python
class Account:
    def __init__(self, balance):
        self.balance = balance
    
    def __bool__(self):
        return self.balance > 0

a = Account(100)
if a:               # True → __bool__
    print("Solvent")

b = Account(0)
if not b:           # True → __bool__ returns False
    print("Bankrupt")
```

### Overview of the most important dunder methods

| Category | Methods | Called when... |
|----------|---------|----------------|
| Creation | `__init__`, `__new__` | An instance is created |
| Representation | `__repr__`, `__str__`, `__format__` | repr(), str(), f-string |
| Comparison | `__eq__`, `__lt__`, `__le__`, `__gt__`, `__ge__` | ==, <, <=, >, >= |
| Hashing | `__hash__` | hash(), dictionary key, set member |
| Bool | `__bool__`, `__len__` | if obj, while obj |
| Container | `__getitem__`, `__setitem__`, `__delitem__`, `__len__`, `__contains__` | obj[x], len(), in |
| Iterator | `__iter__`, `__next__` | for loop, iteration |
| Callable | `__call__` | obj() |
| Arithmetic | `__add__`, `__sub__`, `__mul__`, `__truediv__`, `__mod__` | +, -, *, /, % |
| Reflected | `__radd__`, `__rsub__`, ... | Left operand returns NotImplemented |
| In-place | `__iadd__`, `__isub__`, ... | +=, -=, ... |
| Context Mgr | `__enter__`, `__exit__` | with statement |
| Attributes | `__getattr__`, `__setattr__`, `__delattr__` | obj.x access |

---

### Interview questions - Python Data Model

**Q1: "What is the Python Data Model?"**

> Expected answer: "It is a framework defining how objects interact with language constructs. Through dunder (double-underscore) methods, Python calls special object methods when you use operators, built-in functions, or language constructs. For example, `len(x)` calls `x.__len__()`, and `a + b` calls `a.__add__(b)`. This makes user-defined classes first-class citizens that behave like built-in types."

**Q2: "What is the difference between `__repr__` and `__str__`?"**

> Expected answer: "`__repr__` is for developers: it should be unambiguous, ideally allowing `eval(repr(obj))` to recreate the object. `__str__` is for end users and should be readable. `print()` uses `__str__`, while container displays (lists, dictionaries) use `__repr__`. If I implement only one, I choose `__repr__`, since it is the fallback for `__str__`."

**Q3: "What is `NotImplemented`, and when is it returned?"**

> Expected answer: "It is a special singleton value returned from dunder methods (not raised!) when an operation cannot handle the given type. For example, `Vector.__add__(self, other)` returns `NotImplemented` when `other` is not a Vector. Python then tries the other operand's reflected method, `other.__radd__(self)`. This enables different types to cooperate."

**Q4: "How do you make a class behave like a container?"**

> Expected answer: "Implement the container protocol: `__getitem__` for indexed/keyed access, `__len__` for length, and `__contains__` for `in`. `__getitem__` alone gives iteration, slicing, and membership testing. For a complete container, add `__setitem__`, `__delitem__`, and `__iter__`."

**Q5: "What happens if you define `__eq__` without `__hash__`?"**

> Expected answer: "Python automatically sets `__hash__ = None`, making the object unhashable: it cannot be a dictionary key or set member. This is intentional because equal objects must have equal hashes. Keeping the default identity-based hash would give equal objects different hashes, breaking dictionary/set behavior."

---

## 8. Dict Internals (Hash Table)

### What is a hash table?

Python's `dict` is implemented as a **hash table**, a data structure providing O(1) keyed access on average.

The idea: instead of searching all elements (O(n)), **calculate** an element's location with a hash function.

```
Key "name" → hash("name") → 2342847923 → array index 5
                                             ↓
Array: [ _ | _ | _ | _ | _ | ("name", "Alice") | _ | _ ]
                               index 5
```

### How `dict` works step by step

**1. Insertion (`d["name"] = "Alice"`):**

```python
d = {}
d["name"] = "Alice"

# Internally:
# 1. Compute hash: hash("name") → 2342847923
# 2. Compute index: 2342847923 % table_size → 5
# 3. Put ("name", "Alice") at position 5
```

**2. Reading (`d["name"]`):**

```python
value = d["name"]

# Internally:
# 1. Compute hash: hash("name") → 2342847923
# 2. Compute index: 2342847923 % table_size → 5
# 3. Inspect position 5
# 4. Check the key really is "name" (different keys can share an index)
# 5. Return "Alice"
```

### Hash collisions

A **collision** occurs when two different keys map to the same table index:

```python
# Hypothetically:
hash("name") % 8 = 5
hash("city") % 8 = 5    # same index! COLLISION
```

CPython resolves collisions using **open addressing** with **probing**. When a position is occupied, it looks for another available slot using perturbation-based probing:

```
# Simplified probing:
index = hash(key) % table_size
while table[index] is not empty:
    if table[index].key == key:
        return table[index]     # found it!
    index = next_probe(index)   # try the next position
```

CPython does NOT use ordinary linear probing (`index + 1`); it uses a more sophisticated algorithm that reduces clustering:

```
# CPython probing formula:
perturb = hash_value
index = perturb % table_size
while collision:
    perturb >>= 5
    index = (5 * index + perturb + 1) % table_size
```

### Compact dict (Python 3.6+)

Before Python 3.6, dictionaries used one large table where every slot contained `(hash, key, value)`, leaving many empty slots and wasting memory.

Since Python 3.6 (implementation) / 3.7 (guarantee), dictionaries use **two structures**:

```
1. HASH TABLE (indices) - a small array of indices
   [None, 1, None, 0, 2, None, None, None]
   
2. ENTRIES array (compact, densely populated) - insertion order
   index 0: (hash_of_name,  "name",  "Alice")
   index 1: (hash_of_age,   "age",   30)
   index 2: (hash_of_city,  "city",  "NYC")
```

**Advantages:**
- **Preserves insertion order** (why Python 3.7+ dictionaries retain order!)
- **Less memory** - a densely populated entries array without empty slots
- **Better cache performance** - entries are contiguous in memory

```python
d = {}
d["name"] = "Alice"
d["age"] = 30
d["city"] = "NYC"

list(d.keys())    # ['name', 'age', 'city'] - insertion order, guaranteed since 3.7
```

### Load factor and resizing

A dictionary must not become too full, because this increases collisions. CPython keeps the **load factor below 2/3**:

```
load_factor = number_of_entries / table_size

When load_factor > 2/3 → RESIZE (usually x2)
```

**Resizing is expensive!** All keys must be rehashed and reinserted into a new, larger table.

```python
# Growth example:
d = {}
# Initial table size: 8
# After 5 elements (5/8 = 0.625 < 2/3): OK
# After 6 elements (6/8 = 0.75 > 2/3): RESIZE to 16
# After 10 elements (10/16 = 0.625 < 2/3): OK
# After 11 elements (11/16 = 0.6875 > 2/3): RESIZE to 32
```

### Operation complexity

| Operation | Average case | Worst case |
|-----------|--------------|------------|
| `d[key]` lookup | O(1) | O(n) |
| `d[key] = val` insert | O(1) amortized | O(n) |
| `del d[key]` | O(1) | O(n) |
| `key in d` | O(1) | O(n) |
| Iteration | O(n) | O(n) |

The O(n) worst case occurs when collisions concentrate at the same index; with a good hash function this almost never happens in practice.

**Amortized O(1)** insertion means most insertions are O(1), with occasional O(n) resizing. Averaged across many operations, each is O(1).

### The `hash()` function

```python
# Immutable types have hashes:
hash(42)              # 42
hash("hello")         # -1556667920 (varies between runs!)
hash((1, 2, 3))       # 529344067295497451
hash(frozenset({1}))  # some number

# Mutable types do NOT have hashes:
hash([1, 2])          # TypeError: unhashable type: 'list'
hash({1: 2})          # TypeError: unhashable type: 'dict'
hash({1, 2})          # TypeError: unhashable type: 'set'
```

**Hash randomization (Python 3.3+):** string and bytes hashes are randomized on each run (`PYTHONHASHSEED`). This is a security measure against hash-collision denial-of-service attacks.

```python
# Run 1:
hash("hello")  # -1556667920

# Run 2:
hash("hello")  # 8736278462834 (different!)

# But always the same within one run:
hash("hello") == hash("hello")  # True
```

### dict vs set - the same structure

Internally, a `set` is a **dictionary without values**, using the same hash-table approach:

```python
# A set is essentially a dictionary whose keys are elements, with no values:
s = {1, 2, 3}       # hash table with keys 1, 2, 3
d = {1: None, 2: None, 3: None}  # conceptually similar

# Thus set operations have the same complexities:
x in s          # O(1) - hash lookup
s.add(x)        # O(1) amortized
s.remove(x)     # O(1)
```

### `__hash__` and `__eq__` - rules for dictionary keys

To serve as a dictionary key, an object MUST:
1. Have a `__hash__()` method
2. Have an `__eq__()` method
3. Satisfy **if a == b, then hash(a) == hash(b)** (mandatory!)
4. The reverse does NOT have to hold: hash(a) == hash(b) does not imply a == b (that is a collision)

```python
class BadKey:
    def __init__(self, val):
        self.val = val
    def __hash__(self):
        return 1  # ALL instances have the same hash!
    def __eq__(self, other):
        return isinstance(other, BadKey) and self.val == other.val

# This WORKS but is TERRIBLY slow:
d = {}
for i in range(1000):
    d[BadKey(i)] = i
# Each lookup is O(n): every hash is 1, so everything collides
```

### Practical tips

**1. Size of an empty dictionary:**

```python
import sys
print(sys.getsizeof({}))     # 64 bytes (Python 3.12)
print(sys.getsizeof({1: 1})) # 184 bytes (table allocated)
```

**2. Dictionary comprehension is faster than a loop:**

```python
# Slower:
d = {}
for i in range(1000):
    d[i] = i * i

# Faster:
d = {i: i * i for i in range(1000)}
```

**3. `dict.get()` vs `[]` vs `setdefault()`:**

```python
d = {"a": 1}

d["b"]              # KeyError!
d.get("b")          # None
d.get("b", 0)       # 0 (default)
d.setdefault("b", []).append(1)  # creates [] if absent, then appends 1
```

---

### Interview questions - Dict Internals

**Q1: "How does a Python dictionary work internally?"**

> Expected answer: "A dictionary is a hash table. The key is hashed and its hash mapped to a table index storing the key-value pair. Since Python 3.6/3.7, compact dictionaries use two structures: an index hash table and a densely populated entries array preserving insertion order. Collisions are handled with open addressing and perturbation-based probing."

**Q2: "What happens when a dictionary becomes too full?"**

> Expected answer: "When the load factor exceeds 2/3, the dictionary resizes, usually doubling the table. All keys must be rehashed and reinserted. Hence insertion is amortized O(1): most operations are O(1), with occasional O(n) resizing."

**Q3: "Why can't mutable types be dictionary keys?"**

> Expected answer: "A dictionary relies on keys retaining a constant hash. If a key changed and its hash changed, the dictionary could not find it at the original position. The rule is therefore that only hashable (usually immutable) objects can be keys."

**Q4: "Why do dictionaries preserve order from Python 3.7 onward?"**

> Expected answer: "Because of the compact dictionary implementation. Instead of one table with many empty slots, it uses an index hash table and a densely populated entries array in insertion order. Iteration follows that array, which is inherently ordered. This was a CPython implementation detail in 3.6 and became part of the language specification in 3.7."

**Q5: "How do dictionaries and sets differ internally?"**

> Expected answer: "A set is essentially a dictionary without values: the same hash-table approach, probing mechanism, and operation complexities. A set element corresponds to a dictionary key. Sets therefore have O(1) lookup, insertion, and removal, like dictionaries."

---

## 9. List Internals (Dynamic Array)

### What is a list internally?

A Python list is a **dynamic array**: a contiguous block of memory holding **pointers** (references) to objects, with automatic growth.

```
List [10, "hello", 3.14]:

+---+---+---+---+---+---+---+---+
| * | * | * |   |   |   |   |   |    ← pointer array (allocated = 8)
+---+---+---+---+---+---+---+---+
  |   |   |
  v   v   v
 10  "hello" 3.14                     ← heap objects (different types!)

ob_size = 3 (actual element count)
allocated = 8 (allocated slot count)
```

Unlike C arrays that store actual values, Python lists store **pointers to objects**. This is why a list can contain different types.

### The PyListObject structure

```c
typedef struct {
    PyObject_VAR_HEAD          // ob_refcnt, ob_type, ob_size
    PyObject **ob_item;        // pointer to an array of pointers
    Py_ssize_t allocated;      // number of allocated slots
} PyListObject;
```

- `ob_size` = number of elements (returned by `len()`)
- `allocated` = allocated slot count (always >= ob_size)
- `ob_item` = pointer to a C array of pointers to Python objects

### How lists grow - over-allocation

When `append()` fills a list (`ob_size == allocated`), Python allocates **more space than immediately needed**:

```python
# New-size formula (CPython):
new_allocated = (newsize >> 3) + (3 if newsize < 9 else 6) + newsize
```

In practice, growth looks approximately like this:

```
ob_size:    0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9  → ...
allocated:  0 → 4 → 4 → 4 → 4 → 8 → 8 → 8 → 8 → 16 → ...
```

This makes `append()` **amortized O(1)**. Most appends are O(1), simply setting a pointer; occasional resizing is O(n), copying the pointer array. The average is O(1).

```python
import sys

lst = []
prev_size = sys.getsizeof(lst)
for i in range(20):
    lst.append(i)
    new_size = sys.getsizeof(lst)
    if new_size != prev_size:
        print(f"len={len(lst):2d}, size={new_size} bytes (+{new_size - prev_size})")
        prev_size = new_size

# len= 1, size=88 bytes (+32)    ← space for 4
# len= 5, size=120 bytes (+32)   ← space for 8
# len= 9, size=184 bytes (+64)   ← space for 16
# len=17, size=248 bytes (+64)
```

### Operation complexity

| Operation | Complexity | Explanation |
|-----------|------------|-------------|
| `lst[i]` | O(1) | Direct indexed access (pointer arithmetic) |
| `lst[i] = x` | O(1) | Replace a pointer |
| `lst.append(x)` | O(1) amortized | Occasional resize |
| `lst.pop()` | O(1) | Remove from the end |
| `lst.pop(0)` | **O(n)** | Shift ALL remaining elements left! |
| `lst.insert(0, x)` | **O(n)** | Shift ALL elements right! |
| `lst.insert(i, x)` | O(n-i) | Shift elements from i to the end |
| `x in lst` | **O(n)** | Linear search |
| `lst.remove(x)` | O(n) | Search + shift |
| `lst[a:b]` | O(b-a) | Copy a slice |
| `len(lst)` | O(1) | Read ob_size |
| `lst.extend(other)` | O(k) | k = len(other) |
| `lst.sort()` | O(n log n) | Timsort |

### `pop(0)` and `insert(0, x)` are O(n) - use `deque`!

```python
from collections import deque

# List - SLOW operations at the beginning:
lst = list(range(100000))
lst.pop(0)          # O(n) - shifts 99999 elements
lst.insert(0, 42)   # O(n) - shifts 100000 elements

# Deque - O(1) at both ends:
dq = deque(range(100000))
dq.popleft()        # O(1)
dq.appendleft(42)   # O(1)
```

`deque` is implemented as a **doubly linked list of fixed-size blocks**: O(1) operations at both ends, but O(n) indexed access (`dq[i]`).

### Timsort - Python's sorting algorithm

`list.sort()` and `sorted()` use **Timsort**, a hybrid combining merge sort and insertion sort:

- Finds already sorted portions ("runs")
- Uses insertion sort for small portions (< 64 elements)
- Merges runs intelligently
- **Stable**: equal elements retain their original order
- Best case: O(n) for an already sorted list
- Average/worst case: O(n log n)
- Space: O(n) for merging

```python
# Stable sort - important for sorting on multiple keys:
students = [("Ana", 85), ("Bob", 90), ("Ana", 90)]
students.sort(key=lambda s: s[1])
# [("Ana", 85), ("Bob", 90), ("Ana", 90)]
# Bob and Ana(90) have equal scores and retain their original order
```

### List vs Tuple - memory and performance

```python
import sys

lst = [1, 2, 3, 4, 5]
tup = (1, 2, 3, 4, 5)

print(sys.getsizeof(lst))  # 104 bytes
print(sys.getsizeof(tup))  # 80 bytes (smaller - no allocated field, no over-allocation)
```

Tuples are smaller because they have no `allocated` field and do not over-allocate. CPython also caches small tuple objects for reuse.

---

### Interview questions - List Internals

**Q1: "How is a Python list implemented internally?"**

> Expected answer: "As a dynamic array: a contiguous array of pointers to objects. It has `ob_size` (element count) and `allocated` (allocated slot count). When full, Python allocates extra slots (over-allocation), providing amortized O(1) append."

**Q2: "Why is `list.pop(0)` slow, and what is the alternative?"**

> Expected answer: "`pop(0)` is O(n) because it shifts every remaining element one position left. For efficient operations at both ends, I use `collections.deque`, whose `appendleft()` and `popleft()` are O(1)."

**Q3: "What is Timsort?"**

> Expected answer: "Timsort is the hybrid sorting algorithm Python uses for `list.sort()` and `sorted()`. It combines merge sort and insertion sort: finds sorted runs, uses insertion sort for short sequences, then merges the runs. It is stable, O(n log n) on average and in the worst case, and O(n) when the list is already sorted."

---

## 10. Generators vs Iterators

### Iterator protocol - a reminder

An iterator is an object implementing:
- `__iter__()` - returns itself
- `__next__()` - returns the next item or raises `StopIteration`

```python
lst = [1, 2, 3]
it = iter(lst)       # lst.__iter__() → returns an iterator object

next(it)             # 1  → it.__next__()
next(it)             # 2
next(it)             # 3
next(it)             # StopIteration!
```

An **iterable** has `__iter__()` and can **create** an iterator.
An **iterator** has `__next__()` and **is** the iterator itself.

```python
lst = [1, 2, 3]          # ITERABLE (can create an iterator)
it = iter(lst)            # ITERATOR (can produce the next item)

# A list is iterable but is NOT an iterator:
next(lst)                 # TypeError!

# An iterator IS also iterable:
iter(it) is it            # True (returns itself)
```

### Generators - the easiest way to create an iterator

A generator is a **function using `yield`** instead of `return`. Calling a generator function gives a generator object, which is an iterator:

```python
def countdown(n):
    while n > 0:
        yield n
        n -= 1

gen = countdown(3)
print(type(gen))     # <class 'generator'>

next(gen)    # 3
next(gen)    # 2
next(gen)    # 1
next(gen)    # StopIteration
```

### How generators work internally - freezing a frame

When a function reaches `yield`:
1. It **pauses** execution and returns the yielded value
2. It **freezes** the execution frame (local variables, program counter)
3. The next `next()` call **unfreezes** the frame and resumes where it stopped

```python
def example():
    print("Step 1")
    yield "A"               # pauses here and returns "A"
    print("Step 2")
    yield "B"               # pauses here and returns "B"
    print("Step 3")        # no more yields → StopIteration

gen = example()
# Nothing has executed! Generators are lazy

next(gen)    # prints "Step 1", returns "A"
next(gen)    # prints "Step 2", returns "B"
next(gen)    # prints "Step 3", raises StopIteration
```

Internally, a generator object stores:
- `gi_frame` - the suspended execution frame
- `gi_code` - the generator function's code object
- `gi_running` - whether it is currently executing

### Lazy evaluation - the main advantage

Generators do NOT store all elements in memory. They produce them **on demand** (lazily):

```python
# List - EVERYTHING in memory at once:
lst = [x ** 2 for x in range(10_000_000)]
# Uses ~80MB of RAM!

# Generator - one at a time:
gen = (x ** 2 for x in range(10_000_000))
# Uses ~120 bytes, regardless of size!
```

```python
import sys

lst = [x for x in range(1_000_000)]
gen = (x for x in range(1_000_000))

print(sys.getsizeof(lst))   # 8,448,728 bytes (~8MB)
print(sys.getsizeof(gen))   # 200 bytes
```

### Generator expression vs List comprehension

```python
# List comprehension - creates an in-memory list:
squares_list = [x**2 for x in range(10)]    # [0, 1, 4, 9, ...]

# Generator expression - creates a lazy generator:
squares_gen = (x**2 for x in range(10))     # generator object

# Syntax: [] → list, () → generator
```

### `yield from` - delegation

`yield from` delegates generation to another iterable:

```python
def chain(*iterables):
    for it in iterables:
        yield from it        # equivalent to: for x in it: yield x

list(chain([1, 2], [3, 4], [5]))    # [1, 2, 3, 4, 5]
```

`yield from` is more efficient than `for x in it: yield x` because it avoids Python-level overhead for every element.

### A generator as a coroutine - `send()`

Generators can also **receive** values:

```python
def accumulator():
    total = 0
    while True:
        value = yield total     # yields total, receives value
        total += value

acc = accumulator()
next(acc)              # 0 (initializes the generator and yields the initial total)
acc.send(10)           # 10 (total = 0 + 10, yields 10)
acc.send(20)           # 30 (total = 10 + 20)
acc.send(5)            # 35
```

`send(value)` is like `next()`, but passes a value into the generator, where it becomes the result of the `yield` expression.

### Generator vs Iterator class

```python
# Iterator class - more code, more control:
class Fibonacci:
    def __init__(self, limit):
        self.limit = limit
        self.a, self.b = 0, 1
        self.count = 0
    
    def __iter__(self):
        return self
    
    def __next__(self):
        if self.count >= self.limit:
            raise StopIteration
        value = self.a
        self.a, self.b = self.b, self.a + self.b
        self.count += 1
        return value

# Generator - the same, but much shorter:
def fibonacci(limit):
    a, b = 0, 1
    for _ in range(limit):
        yield a
        a, b = b, a + b

list(fibonacci(8))  # [0, 1, 1, 2, 3, 5, 8, 13]
```

### One pass only!

A generator can be iterated **only once**:

```python
gen = (x for x in range(5))
list(gen)    # [0, 1, 2, 3, 4]
list(gen)    # [] - exhausted!

# A list can be iterated any number of times:
lst = [0, 1, 2, 3, 4]
list(lst)    # [0, 1, 2, 3, 4]
list(lst)    # [0, 1, 2, 3, 4] - always works
```

### Practical use cases

```python
# 1. Reading large files:
def read_large_file(path):
    with open(path) as f:
        for line in f:
            yield line.strip()

# 2. Infinite sequences:
def natural_numbers():
    n = 0
    while True:
        yield n
        n += 1

# 3. Pipeline processing:
def parse(lines):
    for line in lines:
        yield line.split(",")

def filter_active(records):
    for rec in records:
        if rec[2] == "active":
            yield rec

lines = read_large_file("users.csv")
parsed = parse(lines)
active = filter_active(parsed)
# Nothing has executed! Everything is lazy.
# Data flows through the pipeline only when we iterate:
for user in active:
    print(user[0])
```

---

### Interview questions - Generators vs Iterators

**Q1: "What is the difference between an iterator and a generator?"**

> Expected answer: "An iterator is any object implementing `__iter__()` and `__next__()`. A generator is a special iterator created by a function using `yield`: Python automatically implements the iterator protocol. Generators are easier to write and automatically preserve state (local variables) between calls."

**Q2: "What is lazy evaluation, and why is it useful?"**

> Expected answer: "Values are generated on demand rather than upfront. A generator does not keep all elements in memory; it produces them one by one when `next()` is called. This is essential for datasets too large for memory, infinite sequences, and processing pipelines that do not need everything at once."

**Q3: "How do `[x for x in range(n)]` and `(x for x in range(n))` differ?"**

> Expected answer: "Square brackets create a list comprehension: all items are generated immediately and stored in memory. Parentheses create a lazy generator expression that produces items on demand and uses constant memory. For a million elements, a list consumes megabytes; a generator uses roughly 200 bytes."

---

## 11. Decorators Under the Hood

### What is a decorator, really?

A decorator is a **function that receives a function and returns a (new) function**. `@decorator` is just syntactic sugar:

```python
@my_decorator
def say_hello():
    print("Hello!")

# Equivalent to:
def say_hello():
    print("Hello!")
say_hello = my_decorator(say_hello)    # rebinding!
```

### How to write a decorator

```python
def timer(func):
    def wrapper(*args, **kwargs):
        import time
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        print(f"{func.__name__} took {elapsed:.4f}s")
        return result
    return wrapper

@timer
def slow_function(n):
    """Calculates the sum slowly."""
    return sum(range(n))

slow_function(1_000_000)
# slow_function took 0.0312s
```

### Closures - the mechanism behind decorators

Decorators work through **closures**. The `wrapper` function captures `func` from the enclosing scope:

```python
def timer(func):        # func is a free variable
    def wrapper(*args, **kwargs):
        # wrapper sees func from the enclosing scope (closure)
        result = func(*args, **kwargs)
        return result
    return wrapper
```

The wrapper remembers `func` even after `timer()` finishes. That is a closure: a function plus its enclosing scope.

```python
@timer
def add(a, b):
    return a + b

print(add.__closure__)
# (<cell at 0x...: function object at 0x...>,)
# The closure holds a reference to the original add function
```

### The problem: lost metadata

```python
@timer
def add(a, b):
    """Adds two numbers."""
    return a + b

print(add.__name__)    # "wrapper" - WRONG! Should be "add"
print(add.__doc__)     # None - WRONG! Should be "Adds two numbers."
help(add)              # Help on function wrapper - WRONG!
```

### The solution: `functools.wraps`

```python
from functools import wraps

def timer(func):
    @wraps(func)    # copies __name__, __doc__, __module__, etc.
    def wrapper(*args, **kwargs):
        import time
        start = time.perf_counter()
        result = func(*args, **kwargs)
        print(f"{func.__name__} took {time.perf_counter() - start:.4f}s")
        return result
    return wrapper

@timer
def add(a, b):
    """Adds two numbers."""
    return a + b

print(add.__name__)      # "add" - CORRECT
print(add.__doc__)       # "Adds two numbers." - CORRECT
print(add.__wrapped__)   # <function add at 0x...> - access to the original!
```

**`@wraps` is essential in production code.** Without it, debugging, logging, and introspection will not work properly.

### Decorators with arguments

When a decorator needs arguments, add **one more nesting level**:

```python
from functools import wraps

def repeat(n):                         # decorator factory
    def decorator(func):               # actual decorator
        @wraps(func)
        def wrapper(*args, **kwargs):   # wrapper
            for _ in range(n):
                result = func(*args, **kwargs)
            return result
        return wrapper
    return decorator

@repeat(3)          # calls repeat(3) → returns decorator → decorator(greet)
def greet(name):
    print(f"Hello, {name}!")

greet("Ana")
# Hello, Ana!
# Hello, Ana!
# Hello, Ana!
```

Think of it this way: `@repeat(3)` is equivalent to `greet = repeat(3)(greet)`.

### A class-based decorator (with `__call__`)

```python
from functools import wraps

class CountCalls:
    def __init__(self, func):
        wraps(func)(self)
        self.func = func
        self.count = 0
    
    def __call__(self, *args, **kwargs):
        self.count += 1
        print(f"Call #{self.count} to {self.func.__name__}")
        return self.func(*args, **kwargs)

@CountCalls
def say_hi():
    print("Hi!")

say_hi()    # Call #1 to say_hi / Hi!
say_hi()    # Call #2 to say_hi / Hi!
say_hi()    # Call #3 to say_hi / Hi!
print(say_hi.count)  # 3
```

### Stacking decorators

Decorators are applied **bottom-up** (the one closest to the function is applied first):

```python
@decorator_A
@decorator_B
@decorator_C
def func():
    pass

# Equivalent to:
func = decorator_A(decorator_B(decorator_C(func)))

# Wrapper execution order: A → B → C → func → C → B → A
```

### Practical decorators you should know

```python
# 1. @staticmethod - receives neither self nor cls
class Math:
    @staticmethod
    def add(a, b):
        return a + b

# 2. @classmethod - receives cls instead of self
class Date:
    def __init__(self, year, month, day):
        self.year, self.month, self.day = year, month, day
    
    @classmethod
    def from_string(cls, s):
        y, m, d = map(int, s.split("-"))
        return cls(y, m, d)

# 3. @property - getter/setter
class Circle:
    def __init__(self, radius):
        self._radius = radius
    
    @property
    def radius(self):
        return self._radius
    
    @radius.setter
    def radius(self, value):
        if value < 0:
            raise ValueError("Radius must be positive")
        self._radius = value

# 4. @functools.lru_cache - memoization
from functools import lru_cache

@lru_cache(maxsize=128)
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n-1) + fibonacci(n-2)

fibonacci(100)  # instant; without lru_cache it would take forever
```

---

### Interview questions - Decorators

**Q1: "What is a decorator, and how does it work?"**

> Expected answer: "A decorator receives a function and returns a new function, usually a wrapper. `@decorator` is syntactic sugar for `func = decorator(func)`. Internally it works through closures: the wrapper captures the original function from the enclosing scope."

**Q2: "What does `functools.wraps` do, and why does it matter?"**

> Expected answer: "`@wraps(func)` copies the original function's metadata (`__name__`, `__doc__`, `__module__`, `__qualname__`) to the wrapper. Without it, the decorated function loses its name and documentation, harming debugging, logging, and introspection. It also adds `__wrapped__` for access to the original function."

**Q3: "How do you write a decorator that accepts arguments?"**

> Expected answer: "Add another nesting level—a decorator factory. The outer function receives the decorator's arguments, the middle function receives the function being decorated, and the innermost function is the wrapper. For example, `@repeat(3)` first calls `repeat(3)` to return the actual decorator, which then receives the function."

---

## 12. Context Managers Under the Hood

### The problem context managers solve

Resources (files, connections, locks) must **always** be released, even when an exception occurs:

```python
# WRONG - file stays open if an exception occurs:
f = open("data.txt")
data = f.read()          # what if this fails?
f.close()                # this line never executes!

# WITH TRY/FINALLY - works, but is clumsy:
f = open("data.txt")
try:
    data = f.read()
finally:
    f.close()

# WITH A CONTEXT MANAGER - elegant:
with open("data.txt") as f:
    data = f.read()
# f is GUARANTEED to close, even if an exception occurs
```

### `__enter__` and `__exit__`

The `with` statement calls two dunder methods:

```python
with expression as var:
    body

# Internally:
manager = expression              # evaluate expression
var = manager.__enter__()         # call __enter__; result goes into var
try:
    body
except:
    if not manager.__exit__(exc_type, exc_val, exc_tb):
        raise                     # if __exit__ returns False, propagate exc
else:
    manager.__exit__(None, None, None)  # no exception
```

### Writing a class-based context manager

```python
class DatabaseConnection:
    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.conn = None
    
    def __enter__(self):
        self.conn = connect(self.connection_string)
        return self.conn       # this becomes the 'as' variable
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()      # ALWAYS close the connection
        return False           # do not suppress exceptions

with DatabaseConnection("postgres://...") as conn:
    conn.execute("SELECT ...")
# conn is closed whether or not an exception occurs
```

### `__exit__` parameters

```python
def __exit__(self, exc_type, exc_val, exc_tb):
    # With NO exception: all three are None
    # With an exception:
    #   exc_type = exception type (e.g. ValueError)
    #   exc_val = exception instance
    #   exc_tb = traceback object
    
    # Return value:
    #   False (or None) = propagate the exception
    #   True = suppress the exception (use rarely!)
    
    self.conn.close()
    return False
```

### `contextlib.contextmanager` - generator-based

Instead of writing a class with `__enter__`/`__exit__`, you can use a generator:

```python
from contextlib import contextmanager

@contextmanager
def timer(label):
    import time
    start = time.perf_counter()
    try:
        yield               # the 'with' block executes here
    finally:
        elapsed = time.perf_counter() - start
        print(f"{label}: {elapsed:.4f}s")

with timer("Processing"):
    sum(range(1_000_000))
# Processing: 0.0234s
```

The structure is always:

```python
@contextmanager
def my_context():
    # __enter__ logic (setup)
    resource = acquire()
    try:
        yield resource       # value for 'as'
    finally:
        # __exit__ logic (cleanup) - ALWAYS runs
        release(resource)
```

### Nested context managers

```python
# Clumsy nesting:
with open("input.txt") as fin:
    with open("output.txt", "w") as fout:
        fout.write(fin.read())

# More elegant (Python 3.1+):
with open("input.txt") as fin, open("output.txt", "w") as fout:
    fout.write(fin.read())

# With parentheses (Python 3.10+):
with (
    open("input.txt") as fin,
    open("output.txt", "w") as fout,
    open("log.txt", "a") as flog,
):
    data = fin.read()
    fout.write(data)
    flog.write("Done\n")
```

### Useful `contextlib` tools

```python
from contextlib import suppress, redirect_stdout, closing

# suppress - ignore specific exceptions:
with suppress(FileNotFoundError):
    os.remove("temp.txt")    # no error if the file does not exist

# redirect_stdout - redirect print output:
import io
f = io.StringIO()
with redirect_stdout(f):
    print("Hello!")
print(f.getvalue())          # "Hello!\n"

# closing - add close() cleanup to an object without __exit__:
with closing(urllib.request.urlopen("http://...")) as page:
    data = page.read()
```

---

### Interview questions - Context Managers

**Q1: "What is a context manager, and how does `with` work?"**

> Expected answer: "A context manager implements `__enter__` and `__exit__`. `with` calls `__enter__` at the start of the block (its result goes into the `as` variable), then `__exit__` at the end, even if an exception occurs. It guarantees resource cleanup. `__exit__` receives exception information and returns True to suppress it or False to propagate it."

**Q2: "How can you write a context manager without a class?"**

> Expected answer: "Decorate a generator function with `@contextlib.contextmanager`. Code before `yield` acts as `__enter__`, the yielded value goes into the `as` variable, and code after yield (in a `finally` block) acts as `__exit__`. This is shorter and more readable than a class."

**Q3: "Why use `with` instead of `try/finally`?"**

> Expected answer: "Both guarantee cleanup, but `with` is more readable, less error-prone, and encapsulates setup/cleanup in a reusable object. `try/finally` must be written each time; a context manager can be written once and used everywhere."

---

## 13. Asyncio Event Loop

### Synchronous vs Asynchronous

**Synchronous:** each operation blocks until it finishes.

```python
# Synchronous - approximately 3 seconds total:
data1 = fetch(url1)      # waits 1 s
data2 = fetch(url2)      # waits 1 s
data3 = fetch(url3)      # waits 1 s
```

**Asynchronous:** while one operation waits for I/O, something else runs.

```python
# Asynchronous - approximately 1 second total:
data1, data2, data3 = await asyncio.gather(
    fetch(url1),          # all three run "simultaneously"
    fetch(url2),
    fetch(url3),
)
```

### What is an event loop?

An event loop is an **infinite loop** that:
1. Checks which tasks are ready to run
2. Runs ready tasks until the first `await`
3. When a task reaches `await`, pauses it and moves to the next
4. When I/O completes, makes the task ready again

```
Event Loop:
┌─────────────────────────────┐
│                             │
│  1. Take a ready task       │
│  2. Run until await         │
│  3. Pause the task          │
│  4. Check I/O completion    │
│  5. Return to step 1        │
│                             │
└─────────────────────────────┘

Task A: [run]──[await I/O]─────────────[run]──[done]
Task B: ──────[run]──[await I/O]──[run]──[done]
Task C: ─────────────[run]──[await]──[run]──[done]
         ─────────────────────────────────────────→ time
         
All on ONE THREAD! No GIL contention.
```

### Coroutines - async/await

```python
import asyncio

async def fetch_data(url, delay):
    print(f"Fetching {url}...")
    await asyncio.sleep(delay)     # simulates I/O - pauses the coroutine
    print(f"Done {url}")
    return f"Data from {url}"

async def main():
    results = await asyncio.gather(
        fetch_data("api/users", 2),
        fetch_data("api/posts", 1),
        fetch_data("api/comments", 3),
    )
    print(results)

asyncio.run(main())
# Fetching api/users...
# Fetching api/posts...
# Fetching api/comments...
# Done api/posts          (after 1 s)
# Done api/users          (after 2 s)
# Done api/comments       (after 3 s)
# Approximately 3 s total instead of 6 s
```

### Coroutine vs Generator

A coroutine is a **generator function on steroids**. Internally it uses the same mechanism (yield/resume), but with different semantics:

```python
# Generator - produces values:
def gen():
    yield 1
    yield 2

# Coroutine - awaits I/O:
async def coro():
    await asyncio.sleep(1)
    return 42

# A coroutine object must be awaited:
result = await coro()     # OK
result = coro()           # RuntimeWarning: coroutine was never awaited!
```

### Tasks and concurrency

```python
async def main():
    # SEQUENTIAL - one after another:
    result1 = await fetch("url1")     # waits for completion
    result2 = await fetch("url2")     # only then runs this

    # CONCURRENT - create tasks:
    task1 = asyncio.create_task(fetch("url1"))
    task2 = asyncio.create_task(fetch("url2"))
    result1 = await task1
    result2 = await task2

    # OR use gather:
    result1, result2 = await asyncio.gather(
        fetch("url1"),
        fetch("url2"),
    )
```

### `asyncio.run()` vs the event loop

```python
# Python 3.7+ (recommended):
asyncio.run(main())

# Equivalent low-level code:
loop = asyncio.get_event_loop()
try:
    loop.run_until_complete(main())
finally:
    loop.close()
```

### Async iterators and context managers

```python
# Async iterator:
class AsyncRange:
    def __init__(self, n):
        self.n = n
        self.i = 0
    
    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self.i >= self.n:
            raise StopAsyncIteration
        await asyncio.sleep(0.1)
        val = self.i
        self.i += 1
        return val

async for i in AsyncRange(5):
    print(i)

# Async context manager:
class AsyncDB:
    async def __aenter__(self):
        self.conn = await connect_async()
        return self.conn
    
    async def __aexit__(self, *exc):
        await self.conn.close()

async with AsyncDB() as conn:
    await conn.execute("SELECT ...")
```

### Common asyncio mistakes

```python
# 1. Missing await:
async def main():
    result = fetch("url")         # WRONG: returns a coroutine, not its result!
    result = await fetch("url")   # CORRECT

# 2. Blocking the event loop:
async def main():
    time.sleep(5)                 # WRONG: blocks the entire loop!
    await asyncio.sleep(5)        # CORRECT: pauses only this coroutine

    # For CPU-bound or blocking operations:
    result = await asyncio.to_thread(blocking_function, arg)

# 3. Creating a task without awaiting it:
async def main():
    asyncio.create_task(some_coro())    # task may be garbage-collected!
    task = asyncio.create_task(some_coro())
    await task                           # CORRECT
```

---

### Interview questions - Asyncio

**Q1: "How does asyncio achieve concurrency on a single thread?"**

> Expected answer: "Through cooperative multitasking. The event loop executes a coroutine until its first `await`, where it pauses, then moves to the next ready coroutine. When the I/O operation finishes, the paused coroutine resumes. Everything runs on one thread, avoiding GIL contention and race conditions on Python objects."

**Q2: "What is the difference between `await coro()` and `asyncio.create_task(coro())`?"**

> Expected answer: "`await` alone executes the coroutine sequentially, suspending the current coroutine until it finishes. `create_task()` schedules it to run concurrently on the event loop, allowing it to run while the current coroutine does something else. `gather()` conveniently runs several tasks concurrently and waits for all of them."

**Q3: "Why must I not use `time.sleep()` in async code?"**

> Expected answer: "`time.sleep()` blocks the whole thread, including the event loop. No other task can run during the sleep. Instead, use `await asyncio.sleep()`, which suspends only the current coroutine and lets the event loop run other tasks. For blocking operations, use `asyncio.to_thread()`."

---

## 14. Threading vs Multiprocessing vs Asyncio

### Three concurrency models

```
Threading:
┌──────────┐  ┌──────────┐  ┌──────────┐
│ Thread 1 │  │ Thread 2 │  │ Thread 3 │
└─────┬────┘  └─────┬────┘  └─────┬────┘
      │             │             │
      └─────────────┼─────────────┘
                    │
            [One process, one GIL]
            Shared memory

Multiprocessing:
┌──────────┐  ┌──────────┐  ┌──────────┐
│ Process 1│  │ Process 2│  │ Process 3│
│ (own GIL)│  │ (own GIL)│  │ (own GIL)│
└──────────┘  └──────────┘  └──────────┘
  Separate       Separate       Separate
  memory         memory         memory

Asyncio:
┌─────────────────────────────────────┐
│          Event Loop                  │
│  Task A ─→ await ─→ Task B ─→ ...  │
│         One thread, one process      │
└─────────────────────────────────────┘
```

### Which should you use, and when?

| Scenario | Best choice | Why |
|----------|-------------|-----|
| Many HTTP requests | **asyncio** | I/O-bound, thousands of connections, minimal overhead |
| Reading several files | **threading** | I/O-bound, simpler code than asyncio |
| Image processing, ML | **multiprocessing** | CPU-bound, true parallelism |
| Web scraping | **asyncio** or **threading** | I/O-bound, depending on the library |
| Database queries | **threading** or **asyncio** | I/O-bound |
| Mathematical calculations | **multiprocessing** | CPU-bound |
| GUI + background work | **threading** | One thread for the UI, another for work |

### Threading basics

```python
import threading
import time

def download(url):
    print(f"Downloading {url}...")
    time.sleep(2)
    print(f"Done {url}")

threads = []
for url in ["url1", "url2", "url3"]:
    t = threading.Thread(target=download, args=(url,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()       # wait for all to finish

# All three downloads run "simultaneously" - about 2 s instead of 6 s
```

### Threading - synchronization

```python
import threading

lock = threading.Lock()
counter = 0

def safe_increment():
    global counter
    for _ in range(1_000_000):
        with lock:           # a context manager for the lock!
            counter += 1

t1 = threading.Thread(target=safe_increment)
t2 = threading.Thread(target=safe_increment)
t1.start(); t2.start()
t1.join(); t2.join()
print(counter)    # 2_000_000 - correct, because we use a lock
```

### Multiprocessing basics

```python
from multiprocessing import Pool

def cpu_heavy(n):
    return sum(i * i for i in range(n))

with Pool(4) as pool:
    results = pool.map(cpu_heavy, [10**7] * 4)
# 4 processes, each on its own CPU core - true parallelism
```

### `concurrent.futures` - a unified API

```python
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

urls = ["url1", "url2", "url3", "url4"]

# For I/O-bound work (threading):
with ThreadPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(download, urls))

# For CPU-bound work (multiprocessing):
with ProcessPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(cpu_heavy, [10**7] * 4))

# submit + as_completed for different tasks:
from concurrent.futures import as_completed

with ThreadPoolExecutor() as executor:
    futures = {executor.submit(download, url): url for url in urls}
    for future in as_completed(futures):
        url = futures[future]
        result = future.result()
        print(f"{url}: {result}")
```

### Complete comparison

| Feature | Threading | Multiprocessing | Asyncio |
|---------|-----------|-----------------|---------|
| Parallelism | No (GIL) | Yes (true) | No (cooperative) |
| Memory | Shared | Separate (copying) | Shared |
| Overhead | Medium | High (fork/spawn) | Low |
| Scalability | ~100 threads | ~CPU core count | ~10000+ tasks |
| Race conditions | Yes, locks needed | Rare (separate memory) | Rare (cooperative) |
| Best for | I/O-bound | CPU-bound | I/O-bound (many tasks) |
| Debugging | Difficult | Moderate | Moderate |
| Ecosystem | All code works | Requires pickling | Requires async libraries |

---

### Interview questions - Threading vs Multiprocessing vs Asyncio

**Q1: "When would you use threading, multiprocessing, or asyncio?"**

> Expected answer: "Threading for I/O-bound tasks with a moderate number of concurrent operations (dozens). Multiprocessing for CPU-bound tasks requiring true parallelism across cores. Asyncio for I/O-bound tasks with many concurrent operations (thousands of connections), where low overhead matters."

**Q2: "Why doesn't threading speed up CPU-bound Python tasks?"**

> Expected answer: "Because of the GIL: only one thread can execute Python bytecode at a time. For CPU-bound tasks, threads take turns on one core rather than running in parallel. Multiprocessing solves this because every process has its own GIL and can actually run on a separate core."

**Q3: "What is `concurrent.futures`, and why does it exist?"**

> Expected answer: "It is a high-level API unifying threading and multiprocessing under one interface. `ThreadPoolExecutor` and `ProcessPoolExecutor` share the same API, so switching between them requires changing one line. It provides `submit()`, `map()`, and `as_completed()` for task management."

---

## 15. LEGB Scope

### What is scope?

Scope determines **where a variable is visible**. Python uses the **LEGB** lookup rule:

```
L - Local        → inside the current function
E - Enclosing    → in outer functions (closure)
G - Global       → at module level
B - Built-in     → built-ins (print, len, int, ...)
```

Python searches **in this order**, using the first matching variable:

```python
x = "global"                    # G - global

def outer():
    x = "enclosing"             # E - enclosing
    
    def inner():
        x = "local"             # L - local
        print(x)                # "local" (L found first)
    
    inner()

outer()
```

### Local scope

Every function call creates a new local scope:

```python
def func():
    x = 10       # local variable
    print(x)

func()           # 10
print(x)         # NameError: name 'x' is not defined
```

**Important:** Python decides whether a variable is local **at compile time**, not at runtime:

```python
x = 10

def func():
    print(x)     # UnboundLocalError!
    x = 20       # this line makes x LOCAL throughout the function

func()
```

Because `x = 20` appears anywhere in the function, Python treats `x` as local throughout the **entire** function, including lines before the assignment.

### The `global` keyword

```python
counter = 0

def increment():
    global counter       # tell Python to use the GLOBAL variable
    counter += 1

increment()
increment()
print(counter)   # 2
```

Without `global`, `counter += 1` would try to read a nonexistent local `counter` → `UnboundLocalError`.

### The `nonlocal` keyword

`nonlocal` allows access to a variable from an **enclosing** scope (not the global scope!):

```python
def counter():
    count = 0
    
    def increment():
        nonlocal count    # use count from the outer function
        count += 1
        return count
    
    return increment

c = counter()
print(c())    # 1
print(c())    # 2
print(c())    # 3
```

Without `nonlocal count`, `count += 1` would again raise `UnboundLocalError`.

### Closures - a function plus its enclosing scope

A closure is created when an inner function **remembers** variables from an outer function, even after the outer function finishes:

```python
def make_multiplier(factor):
    def multiply(x):
        return x * factor    # factor is a free variable from the enclosing scope
    return multiply

double = make_multiplier(2)
triple = make_multiplier(3)

double(5)    # 10
triple(5)    # 15

# double REMEMBERS factor=2 even long after make_multiplier finishes
print(double.__closure__[0].cell_contents)   # 2
```

### The closure-in-a-loop pitfall

A classic trap:

```python
functions = []
for i in range(5):
    def func():
        return i       # i is a closure variable - the SAME one for all functions!
    functions.append(func)

print([f() for f in functions])   # [4, 4, 4, 4, 4] - ALL return 4!
```

Why? All closures share **the same** variable `i`. Once the loop finishes, `i` is 4.

**Solution 1 - a default argument:**

```python
functions = []
for i in range(5):
    def func(i=i):     # i is captured as a default argument
        return i
    functions.append(func)

print([f() for f in functions])   # [0, 1, 2, 3, 4]
```

**Solution 2 - a factory:**

```python
def make_func(i):
    def func():
        return i       # each func has its OWN enclosing scope
    return func

functions = [make_func(i) for i in range(5)]
print([f() for f in functions])   # [0, 1, 2, 3, 4]
```

### Built-in scope

```python
# Built-in scope contains built-in functions:
print, len, int, str, list, dict, range, type, ...

# You can shadow them, but should not:
list = [1, 2, 3]           # shadowing! list no longer refers to the built-in type
list("hello")              # TypeError! list is now [1, 2, 3]

# Access the original built-in:
import builtins
builtins.list("hello")     # ['h', 'e', 'l', 'l', 'o']
```

### Scope and comprehensions

Since Python 3, comprehensions have **their own scope**:

```python
x = 10
lst = [x for x in range(5)]    # x is LOCAL to the comprehension
print(x)                        # 10 - outer x is unchanged (Python 3)
                                 # In Python 2, it would be 4!

# But an outer variable CAN be read:
factor = 2
lst = [x * factor for x in range(5)]   # factor from the enclosing scope
```

---

### Interview questions - LEGB Scope

**Q1: "Explain Python's LEGB rule."**

> Expected answer: "LEGB is the variable lookup order: Local (inside the function), Enclosing (outer function/closure), Global (module level), Built-in (built-in names). Python searches in that order and uses the first match. `global` allows access to global scope; `nonlocal` allows access to enclosing scope."

**Q2: "What is a closure, and how does it work?"**

> Expected answer: "A closure remembers variables from its enclosing scope even after the outer function finishes. Internally, Python stores these free variables in `__closure__`, a sequence of cell objects. Closures underpin decorators, function factories, and callbacks."

**Q3: "Explain the pitfall with closures in a loop."**

> Expected answer: "When I create functions inside a loop that use the loop variable, they all share a reference to the same variable. After the loop, they all see its final value. Fix this with a default argument, `def f(i=i)`, capturing the current value, or a factory function creating a separate enclosing scope for each iteration."

---

## 16. Metaclasses

### What is a metaclass?

In Python, **classes are objects too**. If classes are objects, something must create them. That something is a **metaclass**, a "class of classes".

```python
class Dog:
    pass

print(type(Dog))       # <class 'type'> - Dog is an instance of type
print(type(type))      # <class 'type'> - even type is an instance of itself!
```

The hierarchy:

```
type (metaclass)
  ↓ creates
Dog (class)
  ↓ creates
rex = Dog() (instance)

type(rex)  → Dog
type(Dog)  → type
type(type) → type (self-reference)
```

### `type()` - two uses

`type()` can:
1. Return an object's type: `type(42)` → `<class 'int'>`
2. **Create a new class dynamically:**

```python
# This class:
class Dog:
    sound = "Woof"
    def speak(self):
        return self.sound

# Is equivalent to:
Dog = type("Dog", (), {"sound": "Woof", "speak": lambda self: self.sound})

# type(name, bases, namespace)
# name = class name ("Dog")
# bases = tuple of parent classes (())
# namespace = dictionary of attributes and methods
```

### Writing a metaclass

```python
class Meta(type):
    def __new__(mcs, name, bases, namespace):
        print(f"Creating class: {name}")
        cls = super().__new__(mcs, name, bases, namespace)
        return cls

class Dog(metaclass=Meta):
    pass
# Creating class: Dog ← printed at CLASS DEFINITION, not instantiation!

class Cat(metaclass=Meta):
    pass
# Creating class: Cat
```

A metaclass's `__new__` runs when the **class is defined**, not when an instance is created. This is the key distinction.

### Practical example - class validation

```python
class ValidatedMeta(type):
    def __new__(mcs, name, bases, namespace):
        # Check that every class has a docstring:
        if name != "Base" and "__doc__" not in namespace:
            raise TypeError(f"Class {name} must have a docstring!")
        
        # Check that all methods have type hints:
        for key, value in namespace.items():
            if callable(value) and not key.startswith("_"):
                hints = getattr(value, "__annotations__", {})
                if "return" not in hints:
                    raise TypeError(f"Method {name}.{key} must have return type hint!")
        
        return super().__new__(mcs, name, bases, namespace)

class Base(metaclass=ValidatedMeta):
    """Base class."""
    pass

class Good(Base):
    """Well documented class."""
    def greet(self, name: str) -> str:
        return f"Hi, {name}"

class Bad(Base):       # TypeError: Class Bad must have a docstring!
    def greet(self):   # No docstring - fails at definition time!
        pass
```

### `__init_subclass__` - a more modern alternative

Since Python 3.6, simple cases can use `__init_subclass__` instead of a metaclass:

```python
class Base:
    def __init_subclass__(cls, required_method=None, **kwargs):
        super().__init_subclass__(**kwargs)
        if required_method and not hasattr(cls, required_method):
            raise TypeError(f"{cls.__name__} must implement {required_method}")

class Plugin(Base, required_method="execute"):
    def execute(self):
        pass

class BadPlugin(Base, required_method="execute"):
    pass  # TypeError: BadPlugin must implement execute
```

### When should you use metaclasses?

**Almost never.** Metaclasses are powerful but make code more complex. Use them only when there is no alternative:

1. **ORM frameworks** (Django, SQLAlchemy) - mapping classes to database tables
2. **API frameworks** - automatic class registration
3. **Validation** - checking a class's structure when defined
4. **Singleton pattern** (although simpler approaches exist)

```python
# Singleton using a metaclass:
class SingletonMeta(type):
    _instances = {}
    
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]

class Database(metaclass=SingletonMeta):
    pass

db1 = Database()
db2 = Database()
print(db1 is db2)   # True - same object
```

### `__new__` vs `__init__` in a class vs a metaclass

```
Metaclass.__new__()   → creates a CLASS (called when the class is defined)
Metaclass.__init__()  → initializes the class
Class.__new__()       → creates an INSTANCE (called by Class())
Class.__init__()      → initializes the instance
```

---

### Interview questions - Metaclasses

**Q1: "What are metaclasses in Python?"**

> Expected answer: "A metaclass is a class of classes: it creates classes just as classes create instances. The default metaclass is `type`. Defining a class effectively calls `type(name, bases, namespace)` to create it. I can write a custom metaclass by inheriting from `type` and overriding `__new__` to control class creation."

**Q2: "When would you use a metaclass?"**

> Expected answer: "Rarely—only when I need to control or validate class structure at definition time, rather than instantiation. Typical examples are ORMs (Django models), automatic plugin registration, and interface enforcement. For simpler cases, `__init_subclass__`, class decorators, or ABCs are better choices."

**Q3: "How does `__new__` differ in an ordinary class and a metaclass?"**

> Expected answer: "In an ordinary class, `__new__` runs when creating an instance. In a metaclass, it runs when creating the class itself—at the `class` definition, not the `Class()` call. The metaclass's `__new__` receives the class name, bases, and namespace dictionary, and returns a class object."

---

## 17. Descriptors

### What is a descriptor?

A descriptor is an object defining **at least one** of `__get__`, `__set__`, or `__delete__`. When placed as a **class attribute**, Python invokes it automatically on attribute access.

Descriptors underpin `@property`, `@classmethod`, `@staticmethod`, and even ordinary methods.

```python
class Descriptor:
    def __get__(self, obj, objtype=None):
        print(f"__get__(obj={obj}, type={objtype})")
        return 42
    
    def __set__(self, obj, value):
        print(f"__set__(obj={obj}, value={value})")
    
    def __delete__(self, obj):
        print(f"__delete__(obj={obj})")

class MyClass:
    attr = Descriptor()    # descriptor as a CLASS ATTRIBUTE

x = MyClass()
x.attr          # __get__(obj=<MyClass>, type=<class MyClass>) → 42
x.attr = 10     # __set__(obj=<MyClass>, value=10)
del x.attr      # __delete__(obj=<MyClass>)
```

### Data descriptor vs Non-data descriptor

**Data descriptor** - has `__set__` and/or `__delete__` (in addition to `__get__`):
- Takes **priority** over the instance's `__dict__`

**Non-data descriptor** - has only `__get__`:
- The instance's `__dict__` takes **priority** over it

```python
# Attribute lookup order:
# 1. Data descriptor (from the class)
# 2. Instance __dict__
# 3. Non-data descriptor (from the class)
# 4. Class __dict__

class DataDesc:
    def __get__(self, obj, objtype=None):
        return "data descriptor"
    def __set__(self, obj, value):
        pass

class NonDataDesc:
    def __get__(self, obj, objtype=None):
        return "non-data descriptor"

class MyClass:
    data = DataDesc()
    non_data = NonDataDesc()

x = MyClass()
x.__dict__["data"] = "instance"
x.__dict__["non_data"] = "instance"

print(x.data)       # "data descriptor" ← data descriptor takes priority!
print(x.non_data)   # "instance" ← instance dictionary takes priority!
```

### How `@property` works internally

`@property` is actually a **data descriptor**. Here is a simplified reimplementation:

```python
class MyProperty:
    def __init__(self, fget=None, fset=None, fdel=None):
        self.fget = fget
        self.fset = fset
        self.fdel = fdel
    
    def __get__(self, obj, objtype=None):
        if obj is None:
            return self           # access through the class, not an instance
        if self.fget is None:
            raise AttributeError("unreadable attribute")
        return self.fget(obj)
    
    def __set__(self, obj, value):
        if self.fset is None:
            raise AttributeError("can't set attribute")
        self.fset(obj, value)
    
    def setter(self, fset):
        return type(self)(self.fget, fset, self.fdel)

class Circle:
    def __init__(self, radius):
        self._radius = radius
    
    @MyProperty
    def radius(self):
        return self._radius
    
    @radius.setter
    def radius(self, value):
        if value < 0:
            raise ValueError
        self._radius = value

c = Circle(5)
c.radius        # calls MyProperty.__get__ → fget(c) → c._radius → 5
c.radius = 10   # calls MyProperty.__set__ → fset(c, 10)
```

### How ordinary methods work - function descriptors

Functions are **non-data descriptors**! Their `__get__` returns a bound method:

```python
class Dog:
    def speak(self):
        return "Woof"

d = Dog()

# Class access - returns a function:
Dog.speak           # <function Dog.speak at 0x...>

# Instance access - __get__ returns a BOUND METHOD:
d.speak             # <bound method Dog.speak of <Dog object>>

# Internally:
Dog.__dict__["speak"].__get__(d, Dog)
# Returns a bound method with self=d
```

This is why `d.speak()` automatically passes `d` as `self`: `function.__get__` creates a bound method.

### `@staticmethod` and `@classmethod` as descriptors

```python
class staticmethod_reimpl:
    def __init__(self, func):
        self.func = func
    
    def __get__(self, obj, objtype=None):
        return self.func           # returns the RAW function, without binding

class classmethod_reimpl:
    def __init__(self, func):
        self.func = func
    
    def __get__(self, obj, objtype=None):
        if objtype is None:
            objtype = type(obj)
        def bound(*args, **kwargs):
            return self.func(objtype, *args, **kwargs)
        return bound               # binds the CLASS as the first argument
```

### A practical descriptor - type validation

```python
class Typed:
    def __init__(self, name, expected_type):
        self.name = name
        self.expected_type = expected_type
    
    def __set_name__(self, owner, name):
        self.name = name           # Python 3.6+ calls this automatically
    
    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return obj.__dict__.get(self.name)
    
    def __set__(self, obj, value):
        if not isinstance(value, self.expected_type):
            raise TypeError(f"{self.name} must be {self.expected_type.__name__}")
        obj.__dict__[self.name] = value

class Person:
    name = Typed("name", str)
    age = Typed("age", int)
    
    def __init__(self, name, age):
        self.name = name      # calls Typed.__set__ → validates
        self.age = age

p = Person("Ana", 25)    # OK
p = Person("Ana", "25")  # TypeError: age must be int
```

### `__set_name__` (Python 3.6+)

Called automatically when a descriptor is placed on a class. It lets the descriptor learn its own name:

```python
class Descriptor:
    def __set_name__(self, owner, name):
        # owner = class in which the descriptor is defined
        # name = attribute name in that class
        self.public_name = name
        self.private_name = f"_{name}"
    
    def __get__(self, obj, objtype=None):
        return getattr(obj, self.private_name, None)
    
    def __set__(self, obj, value):
        setattr(obj, self.private_name, value)
```

---

### Interview questions - Descriptors

**Q1: "What are descriptors in Python?"**

> Expected answer: "A descriptor implements `__get__`, `__set__`, and/or `__delete__`. As a class attribute, Python automatically invokes these methods on attribute access. Descriptors underpin `@property`, `@classmethod`, `@staticmethod`, and ordinary methods (functions are non-data descriptors)."

**Q2: "What is the difference between data and non-data descriptors?"**

> Expected answer: "A data descriptor has `__set__` or `__delete__` and takes priority over the instance's `__dict__`. A non-data descriptor has only `__get__`, and the instance dictionary takes priority. Lookup order: data descriptor → instance dictionary → non-data descriptor."

**Q3: "How does `@property` work internally?"**

> Expected answer: "`@property` is a data descriptor class. It stores getter, setter, and deleter functions. `__get__` calls the getter, while `__set__` calls the setter. As a data descriptor, it takes priority over the instance dictionary: `obj.x` invokes property.__get__ instead of looking in obj.__dict__."

---

## 18. Import System

### How `import` works

When you write `import module`, Python follows several steps:

```
1. Check sys.modules (cache) → return the cached module if present
2. Find the module (finders) → search sys.path
3. Load the module (loaders) → compile and execute code
4. Bind the name → assign the module to a variable
```

### `sys.modules` - the module cache

Every imported module is cached in the `sys.modules` dictionary. Importing it again returns the cached object:

```python
import sys

import json
print("json" in sys.modules)   # True

# A second import does NOT execute the module again:
import json    # no effect; returns the cached version

# You can remove it from the cache and reimport:
del sys.modules["json"]
import json    # now it executes again
```

### `sys.path` - where Python looks for modules

```python
import sys
print(sys.path)
# ['',                              ← current directory
#  '/usr/lib/python3.12',           ← standard library
#  '/usr/lib/python3.12/lib-dynload',
#  '/home/user/.local/lib/python3.12/site-packages',  ← pip packages
#  ...]
```

Search order:
1. **Current directory** (or the script's directory)
2. **PYTHONPATH** environment variable
3. **Standard library**
4. **site-packages** (packages installed with pip)

```python
# Add a custom path:
sys.path.insert(0, "/my/custom/path")
import my_module    # search /my/custom/path first
```

### `import` vs `from ... import`

```python
# import module - imports the WHOLE module; access with dot notation:
import os
os.path.join("a", "b")

# from module import name - imports a SPECIFIC name into the local namespace:
from os.path import join
join("a", "b")

# from module import * - imports EVERYTHING defined by __all__:
from os.path import *    # not recommended - pollutes the namespace
```

### `__all__` - controlling `import *`

```python
# mymodule.py
__all__ = ["public_func", "PublicClass"]

def public_func():
    pass

def _private_func():
    pass

class PublicClass:
    pass

# from mymodule import *
# Imports only public_func and PublicClass
# _private_func is NOT imported
```

### Packages - `__init__.py`

```
mypackage/
├── __init__.py        ← makes the directory a package
├── module_a.py
├── module_b.py
└── subpackage/
    ├── __init__.py
    └── module_c.py
```

```python
# __init__.py executes when the package is imported:
import mypackage           # executes mypackage/__init__.py
from mypackage import module_a
from mypackage.subpackage import module_c
```

`__init__.py` can:
- Be empty (simply marking the package)
- Import from submodules to provide a convenient API
- Define `__all__`

```python
# mypackage/__init__.py
from .module_a import func_a
from .module_b import func_b

# Now the user can write:
from mypackage import func_a    # instead of from mypackage.module_a import func_a
```

### Relative vs Absolute imports

```python
# mypackage/module_a.py

# ABSOLUTE import (always from the top):
from mypackage.module_b import something
from mypackage.subpackage.module_c import other

# RELATIVE import (from the current package):
from .module_b import something          # . = same package
from .subpackage.module_c import other   # .subpackage
from ..other_package import thing        # .. = parent package
```

Relative imports work **only inside packages**, not in top-level scripts.

### Circular imports - problems and solutions

```python
# a.py
from b import func_b     # imports b → b imports a → a is not finished yet!

def func_a():
    return "A"

# b.py
from a import func_a     # PROBLEM: a is still loading!

def func_b():
    return "B"
```

This results in `ImportError` or `AttributeError`.

**Solution 1 - import inside a function (lazy import):**

```python
# a.py
def func_a():
    from b import func_b    # imports only when called
    return func_b()
```

**Solution 2 - restructure the code:**
Move shared code into a third module imported by both.

**Solution 3 - import the module, not a name:**

```python
# a.py
import b                    # imports the module, not a name

def func_a():
    return b.func_b()       # accesses it only when called
```

### `.pyc` files and `__pycache__`

Python compiles `.py` files into bytecode (`.pyc`) and caches it in `__pycache__/`:

```
mymodule.py
__pycache__/
    mymodule.cpython-312.pyc    ← cached bytecode
```

- Checks the `.py` file's timestamp and size
- Recompiles if the `.py` file has changed
- Speeds up loading by skipping parsing and compilation

### `importlib` - programmatic imports

```python
import importlib

# Dynamic import:
module = importlib.import_module("json")
module.dumps({"key": "value"})

# Reload (execute the module again):
importlib.reload(module)
```

---

### Interview questions - Import System

**Q1: "How does Python's import system work?"**

> Expected answer: "Python first checks the `sys.modules` cache. If the module is not cached, it searches paths in `sys.path` (current directory, PYTHONPATH, standard library, site-packages). Once found, it compiles bytecode, executes the module's code, and caches the result in `sys.modules`. A repeated import returns the cached object without executing it again."

**Q2: "What are circular imports, and how do you resolve them?"**

> Expected answer: "A circular import occurs when A imports B, which imports A while A is still loading. Solutions: (1) Lazy imports inside functions instead of at the top of a file. (2) Restructure shared dependencies into a third module. (3) Import modules instead of names—`import a` rather than `from a import func`—so the module object is populated by the time the function is called."

**Q3: "What does `__init__.py` do, and what are relative imports?"**

> Expected answer: "`__init__.py` marks a directory as a Python package and runs when the package is imported. It can be empty or contain convenience imports and `__all__`. Relative imports use dots: `.` for the current package and `..` for its parent. They work inside packages, not top-level scripts."

---

## 19. `__slots__`

### The problem: the default `__dict__`

Every Python instance has a `__dict__`, a dictionary storing its instance attributes:

```python
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

p = Point(1, 2)
print(p.__dict__)    # {'x': 1, 'y': 2}
```

Dictionaries are flexible (attributes can be added dynamically), but **consume considerable memory**: an empty dictionary uses 64+ bytes, and one with contents uses 184+ bytes.

### The solution: `__slots__`

`__slots__` replaces `__dict__` with a **fixed array** of slots:

```python
class Point:
    __slots__ = ('x', 'y')
    
    def __init__(self, x, y):
        self.x = x
        self.y = y

p = Point(1, 2)
print(p.x)           # 1 - works normally
p.z = 3              # AttributeError! Cannot add new attributes
print(hasattr(p, '__dict__'))  # False - no dictionary!
```

### How much memory is saved?

```python
import sys

class WithDict:
    def __init__(self, x, y):
        self.x = x
        self.y = y

class WithSlots:
    __slots__ = ('x', 'y')
    def __init__(self, x, y):
        self.x = x
        self.y = y

d = WithDict(1, 2)
s = WithSlots(1, 2)

print(sys.getsizeof(d) + sys.getsizeof(d.__dict__))  # ~200 bytes
print(sys.getsizeof(s))                                # ~56 bytes

# For a million instances:
# With __dict__: ~200MB
# With __slots__: ~56MB → 3–4 times less memory!
```

### How `__slots__` works internally

Instead of `__dict__`, Python uses **descriptors** (topic 17!) for each slot:

```python
class Point:
    __slots__ = ('x', 'y')

# Python internally creates:
# Point.x = <member_descriptor 'x'> ← descriptor storing a value at a fixed offset
# Point.y = <member_descriptor 'y'>

print(type(Point.x))    # <class 'member_descriptor'>
```

Every slot is a **member descriptor** storing a value directly in the instance at a fixed memory offset, rather than in a dictionary. There is no hash lookup—just direct offset-based access.

### Rules and limitations

**1. No dynamic attributes:**

```python
class Slotted:
    __slots__ = ('x',)

s = Slotted()
s.x = 1       # OK
s.y = 2       # AttributeError!
```

**2. Inheritance - a complication:**

```python
class Base:
    __slots__ = ('x',)

class Child(Base):
    __slots__ = ('y',)    # add NEW slots
    # Child has both x and y

class BadChild(Base):
    pass                   # no __slots__ → gets a __dict__ again!
    # BadChild has x (slot) and __dict__ for everything else
```

**3. No default values in slots:**

```python
class Bad:
    __slots__ = ('x',)
    x = 10                 # Error! This would overwrite the descriptor

# Use __init__ for defaults:
class Good:
    __slots__ = ('x',)
    def __init__(self, x=10):
        self.x = x
```

**4. Combining slots and `__dict__`:**

```python
class Hybrid:
    __slots__ = ('x', '__dict__')   # explicitly include __dict__
    
    def __init__(self):
        self.x = 1      # goes into a slot
        self.y = 2      # goes into __dict__
```

**5. Slots and weak references:**

```python
class NoWeakRef:
    __slots__ = ('x',)

import weakref
obj = NoWeakRef()
weakref.ref(obj)     # TypeError!

# Solution - add __weakref__:
class WithWeakRef:
    __slots__ = ('x', '__weakref__')
```

### When should you use `__slots__`?

**Use it when:**
- You have **many instances** (thousands/millions) of the same type
- Attributes are **known in advance** and will not change
- Memory matters (data classes, ORM models, scientific computing)

**Avoid it when:**
- You have few instances
- You need dynamic attributes
- The class uses complex multiple inheritance

### `__slots__` and dataclasses

```python
from dataclasses import dataclass

@dataclass(slots=True)     # Python 3.10+
class Point:
    x: float
    y: float

p = Point(1.0, 2.0)
p.z = 3.0                  # AttributeError - it has slots!
```

---

### Interview questions - `__slots__`

**Q1: "What is `__slots__`, and why is it used?"**

> Expected answer: "`__slots__` is a class-level tuple replacing the instance `__dict__` with fixed slots. Instead of each instance having a memory-expensive dictionary, attributes occupy fixed offsets inside the instance. I use it with many instances and known attributes; it reduces memory use by a factor of 3–4 and slightly speeds up attribute access."

**Q2: "What are the limitations of `__slots__`?"**

> Expected answer: "Dynamic attributes cannot be added (AttributeError). Subclasses must define `__slots__` too, or they acquire a `__dict__`. Weak references require including `__weakref__` in slots. Default values cannot be placed directly in slots. Multiple inheritance also becomes more complicated."

**Q3: "How does `__slots__` work internally?"**

> Expected answer: "Python creates a member descriptor for each slot. Instead of dictionary lookup (hashing and probing), attribute access goes directly to a fixed memory offset in the instance. It is faster and uses less memory by avoiding dictionary overhead: hash tables, over-allocation, and resizing."

---

## 20. What's New in Python 3.10+

### Structural Pattern Matching (Python 3.10)

`match/case` is Python's answer to switch/case, but **much more powerful**:

```python
def handle_command(command):
    match command.split():
        case ["quit"]:
            print("Quitting")
        case ["hello", name]:
            print(f"Hello, {name}!")
        case ["move", x, y]:
            print(f"Moving to ({x}, {y})")
        case _:
            print("Unknown command")

handle_command("hello Ana")     # Hello, Ana!
handle_command("move 5 10")     # Moving to (5, 10)
handle_command("quit")          # Quitting
handle_command("xyz abc")       # Unknown command
```

### Pattern matching - pattern types

**1. Literal pattern:**

```python
match status:
    case 200:
        print("OK")
    case 404:
        print("Not Found")
    case 500:
        print("Server Error")
```

**2. Capture pattern (binding a variable):**

```python
match point:
    case (0, 0):
        print("Origin")
    case (x, 0):
        print(f"On x-axis at {x}")
    case (0, y):
        print(f"On y-axis at {y}")
    case (x, y):
        print(f"Point at ({x}, {y})")
```

**3. Class pattern:**

```python
from dataclasses import dataclass

@dataclass
class Point:
    x: float
    y: float

match point:
    case Point(x=0, y=0):
        print("Origin")
    case Point(x=x, y=0):
        print(f"On x-axis at {x}")
```

**4. Guard (condition):**

```python
match point:
    case Point(x, y) if x == y:
        print(f"On diagonal at {x}")
    case Point(x, y):
        print(f"Not on diagonal")
```

**5. OR pattern:**

```python
match status:
    case 200 | 201 | 204:
        print("Success")
    case 400 | 401 | 403:
        print("Client error")
```

**6. Mapping pattern (dict):**

```python
match config:
    case {"type": "database", "host": host, "port": port}:
        connect(host, port)
    case {"type": "file", "path": path}:
        open_file(path)
```

### Parenthesized context managers (Python 3.10)

```python
with (
    open("input.txt") as fin,
    open("output.txt", "w") as fout,
    open("log.txt", "a") as flog,
):
    process(fin, fout, flog)
```

### `match` vs `if/elif` - when to use each

```python
# if/elif is better for:
if x > 10:            # conditions, inequalities
    pass
elif x > 5:
    pass

# match is better for:
match data:
    case {"type": "user", "name": name}:    # destructuring
        pass
    case {"type": "post", "title": title}:
        pass
```

### Exception Groups and `except*` (Python 3.11)

```python
# Multiple exceptions at once (from asyncio):
try:
    async with asyncio.TaskGroup() as tg:
        tg.create_task(risky_task_1())
        tg.create_task(risky_task_2())
except* ValueError as eg:
    print(f"ValueErrors: {eg.exceptions}")
except* TypeError as eg:
    print(f"TypeErrors: {eg.exceptions}")
```

### The `Self` type (Python 3.11)

```python
from typing import Self

class Builder:
    def set_name(self, name: str) -> Self:
        self.name = name
        return self    # returns Self instead of "Builder" - also works with inheritance
```

### `tomllib` (Python 3.11)

```python
import tomllib

with open("config.toml", "rb") as f:
    config = tomllib.load(f)
```

### Improved error messages (Python 3.10-3.12)

```python
# Python 3.9:
# SyntaxError: invalid syntax

# Python 3.10+:
# SyntaxError: '{' was never closed
# NameError: name 'prnt' is not defined. Did you mean: 'print'?
# AttributeError: 'str' object has no attribute 'lwer'. Did you mean: 'lower'?
```

### The `type` statement (Python 3.12)

```python
# Before 3.12:
from typing import TypeAlias
Vector: TypeAlias = list[float]

# Python 3.12+:
type Vector = list[float]
type Matrix[T] = list[list[T]]     # with generics!
```

### f-string improvements (Python 3.12)

```python
# Before 3.12 - not possible:
# f"{'hello'}"         SyntaxError
# f"{d['key']}"        required d["key"] or a variable

# Python 3.12+:
f"{'hello'}"           # OK
f"{d['key']}"          # OK
f"{f'{x}'}"            # nested f-strings - OK!
```

### The `@override` decorator (Python 3.12)

```python
from typing import override

class Base:
    def method(self) -> None:
        pass

class Child(Base):
    @override
    def method(self) -> None:    # OK, overrides an existing method
        pass
    
    @override
    def methd(self) -> None:     # ERROR: typo, nothing to override
        pass
```

---

### Interview questions - What's New in Python 3.10+

**Q1: "Explain structural pattern matching in Python."**

> Expected answer: "Python 3.10 introduces `match/case`, which is much more powerful than traditional switch/case. It supports destructuring sequences and dictionaries, class patterns, `if` guards, OR patterns using `|`, and the `_` wildcard. It is useful for unpacking complex data structures and responding to their shape."

**Q2: "What are the most important additions in Python 3.11 and 3.12?"**

> Expected answer: "Python 3.11: ExceptionGroup and `except*` for multiple simultaneous exceptions, the `Self` type for annotations, `tomllib`, and substantial speed improvements (10–60%). Python 3.12: the `type` statement for type aliases, more flexible nested f-strings, the `@override` decorator, and a per-interpreter GIL preparing for free-threaded Python in 3.13."

**Q3: "What is ExceptionGroup, and why does it exist?"**

> Expected answer: "ExceptionGroup contains multiple exceptions that occurred together, typically from an asyncio TaskGroup where several tasks can fail. `except*` handles specific exception types in the group without swallowing the others. Previously, there was no elegant way to handle multiple simultaneous exceptions."

---

