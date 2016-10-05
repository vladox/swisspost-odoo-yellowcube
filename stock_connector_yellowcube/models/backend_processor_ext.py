# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (c) 2016 brain-tec AG (http://www.braintec-group.com)
#    All Right Reserved
#
#    See LICENSE file for full licensing details.
##############################################################################
from openerp.tools.translate import _
from openerp.addons.stock_connector import BackendProcessor
from openerp.addons.connector import backend
from openerp.addons.stock_connector import stock_backend_alpha
from .art_processor import ArtProcessor
from .bar_processor import BarProcessor
from .bur_processor import BurProcessor
from .wab_processor import WabProcessor
from .war_processor import WarProcessor
from .wba_processor import WbaProcessor
from .wbl_processor import WblProcessor
from lxml import etree

# Here we define the backend and the current version
wh_yc_backend = backend.Backend(parent=stock_backend_alpha,
                                version='0.1-yellowcube-1.0')

PROCESSORS_FOR_IMPORT = {
    'WBA': lambda s, f: WbaProcessor(s).yc_read_wba_file(f),
    'WAR': lambda s, f: WarProcessor(s).yc_read_war_file(f),
    'BAR': lambda s, f: BarProcessor(s).yc_read_bar_file(f),
    'BUR': lambda s, f: BurProcessor(s).yc_read_bur_file(f),
}


@wh_yc_backend
class BackendProcessorExt(BackendProcessor):
    """
    This class delegates the creation of all the files needed by YellowCube
    """

    def __init__(self, environment):
        super(BackendProcessorExt, self).__init__(environment)
        self.processors = PROCESSORS_FOR_IMPORT.copy()

    def file_type_is_enable(self, _type):
        _type = _type.lower()
        if _type == 'art':
            return self.backend_record.yc_parameter_sync_products
        if _type == 'wab' or _type == 'war':
            return self.backend_record.yc_parameter_sync_picking_out
        if _type == 'wbl' or _type == 'wba':
            return self.backend_record.yc_parameter_sync_picking_in
        if _type == 'bur':
            return self.backend_record.yc_parameter_sync_inventory_moves
        if _type == 'bar':
            return self.backend_record.yc_parameter_sync_inventory_updates
        return False

    def synchronize(self):
        """
        This method generates ART files, and checks local inconsistencies

        """

        self.backend_record.output_for_debug += 'Looking for input files\n'
        files_to_detect = self.env['stock_connector.file'].search([
            ('type', '=', False),
            ('backend_id', '=', self.backend_record.id),
            ('transmit', '=', 'in'),
            ('state', '=', 'ready'),
            ('name', 'ilike', '%.xml'),
        ])
        for file_to_detect in files_to_detect:
            root = etree.XML(str(file_to_detect.content))
            type_node = root.xpath("//*[local-name() = 'ControlReference']"
                                   "/*[local-name() = 'Type']")
            if type_node:
                file_to_detect.type = type_node[0].text.upper()
            else:
                file_to_detect.state = 'error'
                file_to_detect.info = _('Missing ControlReference with Type')
        files_to_import = self.env['stock_connector.file'].search([
            ('type', '!=', False),
            ('backend_id', '=', self.backend_record.id),
            ('transmit', '=', 'in'),
            ('state', '=', 'ready'),
        ])
        for file_to_import in files_to_import:
            if self.file_type_is_enable(file_to_import.type):
                proc = self.processors.get(file_to_import.type)
                if proc:
                    proc(self, file_to_import)

        self.backend_record.output_for_debug += 'Ready for some exports\n'
        # Generating ART files
        products_to_export = self.yc_find_product_for_art()
        if products_to_export and self.file_type_is_enable('art'):
            self.yc_create_art(products_to_export)

    def yc_create_art(self, products_to_export):
        """
        This method can be overriden by specific implementations

        @param products_to_export: Record set of products to export
        """
        ArtProcessor(self).yc_create_art_file(products_to_export)

    def yc_create_control_reference(self, xml_tools, _type, version):
        """
        Creates the basic ControlReference node used among YC

        @param xml_tools: instance with current file data
        @type xml_tools: XmlTools

        @param _type: YC file type
        @type _type: string

        @param version: Version of the current file XSD
        @type version: string

        @return: ControlReference XML element
        @rtype: etree.Element

        """
        create = xml_tools.create_element
        root = create('ControlReference')
        root.append(create('Type', text=_type.upper()))
        root.append(create('Sender', self.yc_get_parameter('sender')))
        root.append(create('Receiver', self.yc_get_parameter('receiver')))
        root.append(create('Timestamp', text=xml_tools.timestamp))
        root.append(create('OperatingMode',
                           self.yc_get_parameter('operating_mode')))
        root.append(create('Version', version))
        return root

    def yc_find_product_for_art(self):
        """
        Searches for products to export

        @return: List of products that can be exported
        @rtype: RecordList of product.product

        """
        return self.env['product.product'].search([('type', '!=', 'service')])

    def yc_get_parameter(self, name):
        """
        Return the value of the related field on the backend record

        @param name: name of the YC parameter
        @type name: string

        @return: value of the field yc_parameter_<name> in the backend record
        @rtype: <field type>

        """
        name = 'yc_parameter_{0}'.format(name)
        return getattr(self.backend_record, name)

    def yc_save_file(self, root, related_ids, tools, _type, transmit='out',
                     suffix=None):
        """
        Saves the XML file into Odoo

        @param root: root XML node
        @type root: etree.Element

        @param related_ids: related elements with this file
        @type related_ids: [(model:string, res_id:integer)*]

        @param tools: xml tools used for this file
        @type tools: XmlTools

        @param _type: type of file
        @type _type: string

        :param transmit: is the file to be sent, or just received?
        :type string
        """
        output = tools.xml_to_string(root)
        format_args = {
            'sender': self.yc_get_parameter('sender'),
            'type': tools._type,
            'ts': tools.timestamp,
            'suffix': '',
        }
        if suffix is not None:
            format_args['suffix'] = '_%s' % suffix
        elif len(related_ids) == 1:
            format_args['suffix'] = '_%s' % related_ids[0][1]
        filename = '{sender}_{type}_{ts}{suffix}.xml'.format(**format_args)
        vals = {
            'name': filename,
            'type': _type,
            'child_ids': [(0, 0, {'res_model': x[0], 'res_id': x[1]})
                          for x in related_ids],
            'content': output,
            'backend_id': self.backend_record.id,
            'transmit': transmit,
        }
        self.env['stock_connector.file'].create(vals)

    def yc_create_wab_file(self, event):
        return WabProcessor(self).yc_create_wab_file(event)

    def yc_create_wbl_file(self, event):
        return WblProcessor(self).yc_create_wbl_file(event)
