# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (c) 2016 brain-tec AG (http://www.braintec-group.com)
#    All Right Reserved
#
#    See LICENSE file for full licensing details.
##############################################################################
from openerp.tools.translate import _
from .file_processor import FileProcessor, WAB_WAR_ORDERNO_GROUP


class WarProcessor(FileProcessor):
    """
    This class reads a WAR file from Yellowcube

    Version: 1.4
    """
    def __init__(self, backend):
        super(WarProcessor, self).__init__(backend, 'war')

    def yc_read_war_file(self, war_file):
        self.backend_record.output_for_debug +=\
            'Reading WAR file {0}\n'.format(war_file.name)

        errors = []
        related_ids = []
        splits_to_do = []
        try:
            for war in self.path(self.tools.open_xml(war_file.content,
                                                     _type='war'),
                                 '//war:WAR'):
                splits = []
                order_no = self.path(war, '//war:CustomerOrderNo')[0].text
                picking = self.find_binding(order_no,
                                            WAB_WAR_ORDERNO_GROUP).record
                if not picking:
                    errors.append(_('Cannot find binding'
                                    'for order {0}').format(order_no))
                    continue
                splits_to_do.append((picking, splits))
                for war_line in self.path(war, '//war:CustomerOrderDetail'):
                    split = self.yc_read_war_line(errors, order_no, war_line)
                    if split:
                        splits.append(split)
        except Exception as e:
            errors.append(self.tools.format_exception(e))

        if len(splits_to_do) == 0:
            errors.append(_('There are no moves in this file'))

        if errors:
            war_file.state = 'error'
            self.backend_record.output_for_debug +=\
                'WAR file errors:\n{0}\n'.format('\n'.join(errors))
        else:
            for picking, splits in splits_to_do:
                self.yc_process_war_splits(picking, related_ids, splits)
                related = ('stock.picking', picking.id)
                if related not in related_ids:
                    related_ids.append(related)
            war_file.state = 'done'
            war_file.child_ids = [(0, 0, {'res_model': x[0], 'res_id': x[1]})
                                  for x in related_ids]
            self.backend_record.output_for_debug += 'WAR file processed\n'

    def yc_process_war_splits(self, picking, related_ids, splits):
        """
        :param picking:
        :param list related_ids:
        :param dict splits:
        :return:
        """
        for split in splits:
            related = ('stock.pack.operation', split['move'].id)
            if related not in related_ids:
                related_ids.append(related)
            self.env['stock.move'].split(**split)
        picking.action_done()

    def yc_read_war_line(self, errors, order_no, war_line):
        """
        :param list errors:
        :param str order_no:
        :param lxml.etree._ElementTree._ElementTree war_line:
        :return: dict
        """
        pos_no = self.path(war_line, 'war:CustomerOrderPosNo')[0].text
        move = self.find_binding(pos_no, 'CustomerOrderNo{0}'
                                 .format(order_no)).record
        if not move:
            errors.append(_('Cannot find binding for move {0}'
                            ' of order {1}'.format(pos_no,
                                                   order_no)))
            return None
        split = {
            'move': move,
        }
        qty_uom = self.path(war_line, 'war:QuantityUOM')[0]
        split['qty'] = float(qty_uom.text)
        uom_code = move.product_uom_id.iso_code
        if uom_code != qty_uom.get('QuantityISO'):
            errors.append(_('Move {0} differ'
                            'in ISO code'.format(pos_no)))
            return None
        return split
