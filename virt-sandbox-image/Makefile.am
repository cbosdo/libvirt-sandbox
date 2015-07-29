POD_FILES = \
	virt-sandbox-image.pod \
	$(NULL)
EXTRA_DIST = $(POD_FILES)

man1_MANS = \
	virt-sandbox-image.1 \
	$(NULL)

POD2MAN = pod2man -c "Virt-Sanbox Image Tool" -r "$(PACKAGE)-$(VERSION)"

virt-sandbox-image.1: virt-sandbox-image.pod Makefile
	$(AM_V_GEN)$(POD2MAN) $< $(srcdir)/$@

CLEANFILES = $(man1_MANS)

virt_sandbox_image_SOURCES = virt-sandbox-image.py

install-data-local:
		cp $(srcdir)/virt-sandbox-image.py $(DESTDIR)/virt-sandbox-image.py

uninstall-local:
		rm -f $(DESTDIR)/virt-sandbox-image.py
