repo_docs := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
repo_root := $(abspath $(repo_docs)/..)
sources := $(wildcard $(repo_root)/pympress/*.py)

.INTERMEDIATE:index.rst

%.tar:_build/index.html
	tar cf $@ -C $(repo_docs)_build .

_build/index.html:index.rst
	sphinx-build -b html $(repo_docs) $(repo_docs)/_build

pympress.rst:$(sources)
	sphinx-apidoc -EMTo $(repo_docs) $(repo_root)/pympress

index.rst:pympress.rst
	@mv $< $@

clean:
	rm -rf _build

