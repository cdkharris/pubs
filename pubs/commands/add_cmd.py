from __future__ import unicode_literals

import argparse
from ..uis import get_ui
from .. import p3
from .. import bibstruct
from .. import content
from .. import repo
from .. import paper
from .. import templates
from .. import apis
from .. import pretty
from .. import utils
from .. import endecoder
from ..completion import CommaSeparatedTagsCompletion


class ValidateDOI(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        doi = values
        new_doi = utils.standardize_doi(doi)
        setattr(namespace, self.dest, new_doi)


def parser(subparsers, conf):
    parser = subparsers.add_parser('add', help='add a paper to the repository')
    parser.add_argument('bibfile', nargs='?', default=None,
                        help='bibtex file')
    parser.add_argument('-D', '--doi', help='doi number to retrieve the bibtex entry, if it is not provided', default=None, action=ValidateDOI)
    parser.add_argument('-I', '--isbn', help='isbn number to retrieve the bibtex entry, if it is not provided', default=None)
    parser.add_argument('-X', '--arxiv', help='arXiv ID to retrieve the bibtex entry, if it is not provided', default=None)
    parser.add_argument('-d', '--docfile', help='pdf or ps file', default=None)
    parser.add_argument('-t', '--tags', help='tags associated to the paper, separated by commas',
                        default=None
                        ).completer = CommaSeparatedTagsCompletion(conf)
    parser.add_argument('-k', '--citekey', help='citekey associated with the paper;\nif not provided, one will be generated automatically.',
                        default=None, type=p3.u_maybe)
    parser.add_argument('-L', '--link', action='store_false', dest='copy', default=True,
                        help="don't copy document files, just create a link.")
    parser.add_argument('-M', '--move', action='store_true', dest='move', default=False,
                        help="move document instead of of copying (ignored if --link).")
    return parser


def bibentry_from_editor(conf, ui, rp):
    again = True
    bibstr = templates.add_bib
    while again:
        try:
            bibstr = ui.editor_input(initial=bibstr, suffix='.bib')
            if bibstr == templates.add_bib:
                again = ui.input_yn(
                    question='Bibfile not edited. Edit again ?',
                    default='y')
                if not again:
                    ui.exit(0)
            else:
                bibentry = rp.databroker.verify(bibstr)
                bibstruct.verify_bibdata(bibentry)
                # REFACTOR Generate citykey
                again = False

        except endecoder.EnDecoder.BibDecodingError:
            again = ui.input_yn(
                question='Invalid bibfile. Edit again?',
                default='y')
            if not again:
                ui.exit()

    return bibentry


def command(conf, args):
    """
    :param bibfile: bibtex file (in .bib, .bibml or .yaml format.
    :param docfile: path (no url yet) to a pdf or ps file
    """

    ui = get_ui()
    bibfile = args.bibfile
    docfile = args.docfile
    tags = args.tags
    citekey = args.citekey

    rp = repo.Repository(conf)

    # get bibtex entry
    if bibfile is None:
        if args.doi is None and args.isbn is None and args.arxiv is None:
            bibentry = bibentry_from_editor(conf, ui, rp)
        else:
            bibentry = None
            try:
                if args.doi is not None:
                    bibentry_raw = apis.doi2bibtex(args.doi)
                    bibentry = rp.databroker.verify(bibentry_raw)
                    if bibentry is None:
                        raise apis.ReferenceNotFoundException(
                            'invalid doi {} or unable to retrieve bibfile from it.'.format(args.doi))
                elif args.isbn is not None:
                    bibentry_raw = apis.isbn2bibtex(args.isbn)
                    bibentry = rp.databroker.verify(bibentry_raw)
                    if bibentry is None:
                        raise apis.ReferenceNotFoundException(
                            'invalid isbn {} or unable to retrieve bibfile from it.'.format(args.isbn))
                    # TODO distinguish between cases, offer to open the error page in a webbrowser.
                    # TODO offer to confirm/change citekey
                elif args.arxiv is not None:
                    bibentry_raw = apis.arxiv2bibtex(args.arxiv)
                    bibentry = rp.databroker.verify(bibentry_raw)
                    if bibentry is None:
                        raise apis.ReferenceNotFoundException(
                            'invalid arxiv id {} or unable to retrieve bibfile from it.'.format(args.arxiv_id))
            except apis.ReferenceNotFoundException as e:
                ui.error(e.message)
                ui.exit(1)
    else:
        bibentry_raw = content.get_content(bibfile, ui=ui)
        bibentry = rp.databroker.verify(bibentry_raw)
        if bibentry is None:
            ui.error('invalid bibfile {}.'.format(bibfile))

    # citekey

    citekey = args.citekey
    if citekey is None:
        base_key = bibstruct.extract_citekey(bibentry)
        citekey = rp.unique_citekey(base_key)
    elif citekey in rp:
        ui.error('citekey already exist {}.'.format(citekey))
        ui.exit(1)

    p = paper.Paper.from_bibentry(bibentry, citekey=citekey)

    # tags

    if tags is not None:
        p.tags = set(tags.split(','))

    # document file

    bib_docfile = bibstruct.extract_docfile(bibentry)
    if docfile is None:
        docfile = bib_docfile
    elif bib_docfile is not None:
        ui.warning(('Skipping document file from bib file '
                    '{}, using {} instead.').format(bib_docfile, docfile))

    # create the paper
    copy = args.copy
    if copy is None:
        copy = conf['main']['doc_add'] in ('copy', 'move')
    move = args.move
    if move is None:
        move = conf['main']['doc_add'] == 'move'

    rp.push_paper(p)
    ui.message('added to pubs:\n{}'.format(pretty.paper_oneliner(p)))
    if docfile is not None:
        rp.push_doc(p.citekey, docfile, copy=copy or args.move)
        if copy:
            if move:
                content.remove_file(docfile)

        if copy:
            if move:
                ui.message('{} was moved to the pubs repository.'.format(docfile))
            else:
                ui.message('{} was copied to the pubs repository.'.format(docfile))

    rp.close()
