from PySide6.QtCore import Qt

from unused_pkg_remover.gui import NumericTableItem, format_size, size_color


class TestFormatSize:
    def test_bytes(self):
        assert format_size(0) == "0.0B"
        assert format_size(500) == "500.0B"
        assert format_size(1023) == "1023.0B"

    def test_kilobytes(self):
        assert format_size(1024) == "1.0KB"
        assert format_size(1536) == "1.5KB"
        assert format_size(1048575) == "1024.0KB"

    def test_megabytes(self):
        assert format_size(1048576) == "1.0MB"
        assert format_size(52428800) == "50.0MB"

    def test_gigabytes(self):
        assert format_size(1073741824) == "1.0GB"
        assert format_size(2147483648) == "2.0GB"

    def test_terabytes(self):
        assert format_size(1099511627776) == "1.0TB"

    def test_petabytes(self):
        assert format_size(1125899906842624) == "1.0PB"


class TestSizeColor:
    def test_large_red(self):
        color = size_color(101 * 1024 * 1024)
        assert color.name() == "#f97583"

    def test_medium_orange(self):
        color = size_color(11 * 1024 * 1024)
        assert color.name() == "#ffab70"

    def test_small_green(self):
        color = size_color(1024)
        assert color.name() == "#7ee787"

    def test_boundary_large(self):
        color = size_color(100 * 1024 * 1024 + 1)
        assert color.name() == "#f97583"

    def test_boundary_medium(self):
        color = size_color(100 * 1024 * 1024)
        assert color.name() == "#ffab70"
        color = size_color(10 * 1024 * 1024 + 1)
        assert color.name() == "#ffab70"

    def test_boundary_small(self):
        color = size_color(10 * 1024 * 1024)
        assert color.name() == "#7ee787"


class TestNumericTableItem:
    def test_less_than_with_user_role_data(self):
        a = NumericTableItem()
        a.setData(Qt.UserRole, 100)
        b = NumericTableItem()
        b.setData(Qt.UserRole, 200)
        assert (a < b) is True
        assert (b < a) is False

    def test_equal_values(self):
        a = NumericTableItem()
        a.setData(Qt.UserRole, 100)
        b = NumericTableItem()
        b.setData(Qt.UserRole, 100)
        assert (a < b) is False

    def test_returns_false_when_no_user_data(self):
        a = NumericTableItem()
        b = NumericTableItem()
        assert (a < b) is False

    def test_handles_none_other(self):
        a = NumericTableItem()
        a.setData(Qt.UserRole, 100)
        assert (a < None) is False
