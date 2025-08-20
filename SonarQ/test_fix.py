#!/usr/bin/env python3

import sys
import os
sys.path.append('.')

from batch_fix import main

if __name__ == "__main__":
    # Test with simple arguments
    sys.argv = ['test_fix.py', 'source_bug', '--fix', '--prompt', 'Fix security issues', '--output', 'source_bug/fixed']
    main()