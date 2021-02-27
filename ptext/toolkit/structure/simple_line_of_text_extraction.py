import typing
from functools import cmp_to_key

from ptext.io.read.types import Decimal
from ptext.pdf.canvas.datastructure.disjoint_set import disjointset
from ptext.pdf.canvas.event.begin_page_event import BeginPageEvent
from ptext.pdf.canvas.event.chunk_of_text_render_event import (
    ChunkOfTextRenderEvent,
    LeftToRightComparator,
)
from ptext.pdf.canvas.event.end_page_event import EndPageEvent
from ptext.pdf.canvas.event.event_listener import Event, EventListener
from ptext.pdf.canvas.geometry.rectangle import Rectangle
from ptext.pdf.canvas.layout.paragraph import LineOfText, LayoutElement
from ptext.pdf.page.page import Page


class SimpleLineOfTextExtraction(EventListener):
    def __init__(self):
        self.chunks_of_text: typing.List[ChunkOfTextRenderEvent] = []
        self.current_page_number = -1
        self.current_page: typing.Optional[Page] = None
        self.lines_of_text_per_page: typing.Dict[int, typing.List[LineOfText]] = {}

    def event_occurred(self, event: Event) -> None:
        if isinstance(event, ChunkOfTextRenderEvent):
            self.chunks_of_text.append(event)
        if isinstance(event, BeginPageEvent):
            self.current_page = event.get_page()
            self.current_page_number += 1
            self.chunks_of_text = []
        if isinstance(event, EndPageEvent):
            self._end_page(event.get_page())

    def get_lines_of_text(self, page: int) -> typing.List[LineOfText]:
        return self.lines_of_text_per_page.get(page, [])

    def _end_page(self, page: Page):

        # build initial disjointset
        chunks_of_text_disjoint_set = disjointset()
        for x in self.chunks_of_text:
            chunks_of_text_disjoint_set.add(x)

        # merge all ChunkOfText objects that represent a line of text
        for c0 in chunks_of_text_disjoint_set:
            for c1 in chunks_of_text_disjoint_set:
                if c0 == c1:
                    continue
                r0 = c0.baseline_bounding_box
                r1 = c1.baseline_bounding_box
                if r0.y != r1.y:
                    continue
                gap = max(r1.x - (r0.x + r0.width), r0.x - (r1.x + r1.width))
                space_gap = (
                    c0.get_space_character_width_estimate()
                    if r0.x < r1.x
                    else c1.get_space_character_width_estimate()
                )
                if gap < space_gap * Decimal(2):
                    chunks_of_text_disjoint_set.union(c0, c1)

        # combine partitions into LineOfText objects
        lines_of_text: typing.List[LineOfText] = []
        for chunks_of_text_partition in chunks_of_text_disjoint_set.sets():
            # sort
            chunks_of_text: typing.List[ChunkOfTextRenderEvent] = [
                x for x in chunks_of_text_partition
            ]
            sorted(chunks_of_text, key=cmp_to_key(LeftToRightComparator.cmp))

            # determine text
            txt = ""
            for i, c in enumerate(chunks_of_text):
                if i == 0:
                    txt += c.text
                    continue
                # decide whether we need to insert space or not
                gap = c.baseline_bounding_box.x - (
                    chunks_of_text[i - 1].baseline_bounding_box.x
                    + chunks_of_text[i - 1].baseline_bounding_box.width
                )
                space_gap = chunks_of_text[i - 1].get_space_character_width_estimate()
                if gap > space_gap:
                    txt += " "
                txt += c.text

            # build LineOfText
            l: LayoutElement = LineOfText(
                text=txt,
                font=chunks_of_text[0].font,
                font_size=chunks_of_text[0].font_size,
                font_color=chunks_of_text[0].font_color,
            ).set_bounding_box(
                Rectangle(
                    chunks_of_text[0].baseline_bounding_box.x,
                    chunks_of_text[0].baseline_bounding_box.y,
                    chunks_of_text[-1].baseline_bounding_box.x
                    + chunks_of_text[-1].baseline_bounding_box.width
                    - chunks_of_text[0].baseline_bounding_box.x,
                    chunks_of_text[0].baseline_bounding_box.height,
                )
            )
            assert isinstance(l, LineOfText)
            lines_of_text.append(l)

        # add to dict
        self.lines_of_text_per_page[self.current_page_number] = lines_of_text