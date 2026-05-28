import io
import textwrap
import pytest
from parser import parse_price_full, PriceRow


def xml_stream(body: str) -> io.BytesIO:
    return io.BytesIO(textwrap.dedent(body).strip().encode("utf-8"))


# ── Happy path ───────────────────────────────────────────────────────────────

def test_parses_basic_items():
    stream = xml_stream("""
        <Root>
          <Items>
            <Item>
              <ItemCode>7290000000001</ItemCode>
              <ItemName>חלב 3%</ItemName>
              <ItemPrice>6.90</ItemPrice>
              <PriceUpdateDate>2026-05-28 03:40:00</PriceUpdateDate>
            </Item>
            <Item>
              <ItemCode>7290000000002</ItemCode>
              <ItemName>לחם אחיד</ItemName>
              <ItemPrice>11.50</ItemPrice>
              <PriceUpdateDate>2026-05-28 03:40:00</PriceUpdateDate>
            </Item>
          </Items>
        </Root>
    """)
    rows = list(parse_price_full(stream))
    assert len(rows) == 2
    assert rows[0] == PriceRow(
        barcode="7290000000001",
        item_name="חלב 3%",
        price=6.90,
        updated_at="2026-05-28T03:40:00+00:00",
    )
    assert rows[1].barcode == "7290000000002"
    assert rows[1].price == 11.50


def test_price_is_float():
    stream = xml_stream("""
        <Root><Items>
          <Item>
            <ItemCode>111</ItemCode>
            <ItemName>test</ItemName>
            <ItemPrice>13.99</ItemPrice>
            <PriceUpdateDate>2026-05-28 00:00:00</PriceUpdateDate>
          </Item>
        </Items></Root>
    """)
    rows = list(parse_price_full(stream))
    assert rows[0].price == 13.99
    assert isinstance(rows[0].price, float)


# ── Filtering / skipping ─────────────────────────────────────────────────────

def test_skips_zero_price():
    stream = xml_stream("""
        <Root><Items>
          <Item>
            <ItemCode>111</ItemCode>
            <ItemName>free item</ItemName>
            <ItemPrice>0.00</ItemPrice>
            <PriceUpdateDate>2026-05-28 00:00:00</PriceUpdateDate>
          </Item>
        </Items></Root>
    """)
    assert list(parse_price_full(stream)) == []


def test_skips_negative_price():
    stream = xml_stream("""
        <Root><Items>
          <Item>
            <ItemCode>111</ItemCode>
            <ItemName>bad</ItemName>
            <ItemPrice>-5.00</ItemPrice>
            <PriceUpdateDate>2026-05-28 00:00:00</PriceUpdateDate>
          </Item>
        </Items></Root>
    """)
    assert list(parse_price_full(stream)) == []


def test_skips_missing_barcode():
    stream = xml_stream("""
        <Root><Items>
          <Item>
            <ItemName>no barcode</ItemName>
            <ItemPrice>5.00</ItemPrice>
            <PriceUpdateDate>2026-05-28 00:00:00</PriceUpdateDate>
          </Item>
        </Items></Root>
    """)
    assert list(parse_price_full(stream)) == []


def test_skips_empty_barcode():
    stream = xml_stream("""
        <Root><Items>
          <Item>
            <ItemCode>  </ItemCode>
            <ItemName>no barcode</ItemName>
            <ItemPrice>5.00</ItemPrice>
            <PriceUpdateDate>2026-05-28 00:00:00</PriceUpdateDate>
          </Item>
        </Items></Root>
    """)
    assert list(parse_price_full(stream)) == []


def test_skips_empty_name():
    stream = xml_stream("""
        <Root><Items>
          <Item>
            <ItemCode>7290000000001</ItemCode>
            <ItemName></ItemName>
            <ItemPrice>5.00</ItemPrice>
            <PriceUpdateDate>2026-05-28 00:00:00</PriceUpdateDate>
          </Item>
        </Items></Root>
    """)
    assert list(parse_price_full(stream)) == []


def test_skips_unparseable_price():
    stream = xml_stream("""
        <Root><Items>
          <Item>
            <ItemCode>7290000000001</ItemCode>
            <ItemName>test</ItemName>
            <ItemPrice>N/A</ItemPrice>
            <PriceUpdateDate>2026-05-28 00:00:00</PriceUpdateDate>
          </Item>
        </Items></Root>
    """)
    assert list(parse_price_full(stream)) == []


# ── Date formats ─────────────────────────────────────────────────────────────

def test_date_with_time():
    stream = xml_stream("""
        <Root><Items>
          <Item>
            <ItemCode>111</ItemCode>
            <ItemName>test</ItemName>
            <ItemPrice>5.00</ItemPrice>
            <PriceUpdateDate>2026-05-28 10:30:00</PriceUpdateDate>
          </Item>
        </Items></Root>
    """)
    rows = list(parse_price_full(stream))
    assert rows[0].updated_at == "2026-05-28T10:30:00+00:00"


def test_date_only_no_time():
    stream = xml_stream("""
        <Root><Items>
          <Item>
            <ItemCode>111</ItemCode>
            <ItemName>test</ItemName>
            <ItemPrice>5.00</ItemPrice>
            <PriceUpdateDate>2026-05-28</PriceUpdateDate>
          </Item>
        </Items></Root>
    """)
    rows = list(parse_price_full(stream))
    assert rows[0].updated_at == "2026-05-28T00:00:00+00:00"


def test_missing_date_uses_epoch():
    stream = xml_stream("""
        <Root><Items>
          <Item>
            <ItemCode>111</ItemCode>
            <ItemName>test</ItemName>
            <ItemPrice>5.00</ItemPrice>
          </Item>
        </Items></Root>
    """)
    rows = list(parse_price_full(stream))
    assert len(rows) == 1
    assert "1970" in rows[0].updated_at  # epoch fallback


# ── Large file / streaming ───────────────────────────────────────────────────

def test_handles_many_items():
    items_xml = "\n".join(
        f"""<Item>
              <ItemCode>{i:013d}</ItemCode>
              <ItemName>product {i}</ItemName>
              <ItemPrice>{(i % 100) + 1}.00</ItemPrice>
              <PriceUpdateDate>2026-05-28 00:00:00</PriceUpdateDate>
            </Item>"""
        for i in range(1, 10001)
    )
    stream = xml_stream(f"<Root><Items>{items_xml}</Items></Root>")
    rows = list(parse_price_full(stream))
    assert len(rows) == 10000


def test_yields_items_not_list():
    """parse_price_full must be a generator, not return a list."""
    import types
    stream = xml_stream("<Root><Items></Items></Root>")
    result = parse_price_full(stream)
    assert isinstance(result, types.GeneratorType)
