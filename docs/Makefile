repo_docs := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
repo_root := $(abspath $(repo_docs)/..)
pysources := $(wildcard $(repo_root)/pympress/*.py)


.PHONY:update clean
update:
	make -C source html
	-mv source/_build/html/* ./
	#sphinx-build -b html $(repo_docs)/source $(repo_docs)/source/_build

clean:
	rm -rf source/_build _modules _sources _static

