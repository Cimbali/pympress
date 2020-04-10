deps:
	dnf -y install python3 python3-pip python3-setuptools python3-wheel python3-babel jq
	python3 -m pip --disable-pip-version-check install -e .[babel]

catalog: deps
	./scripts/poedit.sh download
	python3 setup.py compile_catalog

srpm: catalog
	python3 setup.py bdist_rpm --source-only --dist-dir=$(outdir)


.PHONY:deps catalog srpm
