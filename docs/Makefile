
.PHONY:update clean
update:
	@cp ../README.md source/README.md && make -C source html && rm source/README.md

clean:
	@rm -rf source/_build _modules _sources _static
	@rm -f *.html objects.inv searchindex.js

