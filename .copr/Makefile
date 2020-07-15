deps:
	dnf -y install python3 python3-pip python3-setuptools python3-wheel python3-babel python-vlc jq

catalog: deps
	# public read-only token to download up-to-date translate strings
	poeditor_api_token=7a666b44c0985d16a7b59748f488275c ./scripts/poedit.sh download

srpm: catalog
	python3 setup.py bdist_rpm --source-only --dist-dir=$(outdir)


.PHONY:deps catalog srpm
