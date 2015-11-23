repo_docs := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
repo_root := $(abspath $(repo_docs)/..)
sources := $(wildcard $(repo_root)/pympress/*.py) $(repo_root)/bin/pympress

.INTERMEDIATE:pympress.rst

%.tar:_build/pympress.html
	tar cf $@ -C _build .

_build/pympress.html:pympress.rst
	sphinx-build -b html $(repo_docs) $(repo_docs)/_build

pympress.rst:$(sources)
	sphinx-apidoc -EMTo $(repo_docs) $(repo_root)/pympress

clean:
	rm -rf _build

