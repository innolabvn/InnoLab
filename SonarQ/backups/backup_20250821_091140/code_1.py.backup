
import re 

def rethrow_same_exception(value: str) -> int:
    try:
        return int(value)
    except ValueError as e:
        raise e 


# ---------
# 2) BUGS (7)
# ---------

def self_assign_example() -> int:
    x = 5
    x = x  # BUG
    return x


def self_assign_in_loop(items) -> int:
    total = 0
    for n in items[:1]:  
        total = total 
        total =+ n     
    return total


def ignore_default_param(n: int = 42) -> int:
    n = 0  
    return n


def redundant_regex(s: str) -> bool:
    pattern = re.compile(r"^(?:cat|dog|cat)$")  
    return bool(pattern.match(s))


def plus_equals_typo() -> int:
    count = 0
    count =+ 5  
    return count


def loop_one_iteration(seq):
    found = None
    for item in seq:
        found = item
        break  
    return found


def identical_comparison(a):
    return a == a 


# Keep a simple entry point to avoid side effects during scans
if __name__ == "__main__":
    pass
