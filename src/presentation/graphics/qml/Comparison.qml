import QtQuick 2.15

Rectangle {
    id: root
    width: 1920
    height: 1080
    property real frameProgress: 0.0
    property int frameIndex: 0
    color: graphicsSpec.design.background_hex

    readonly property int safe: graphicsSpec.design.safe_margin_px
    readonly property color accent: graphicsSpec.design.accent_hex
    readonly property color fg: graphicsSpec.design.foreground_hex
    readonly property var entries: graphicsSpec.items

    Text {
        x: safe
        y: safe
        width: parent.width - safe * 2
        text: graphicsSpec.title_ar
        color: fg
        font.family: graphicsSpec.design.font_family
        font.pixelSize: 68
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignRight
        layoutDirection: Qt.RightToLeft
    }
    Repeater {
        model: Math.min(entries.length, 2)
        delegate: Rectangle {
            required property int index
            property var entry: entries[index]
            x: index === 0 ? safe : root.width / 2 + 28
            y: 250
            width: root.width / 2 - safe - 28
            height: 650
            radius: 28
            color: Qt.rgba(0.08, 0.07, 0.06, 0.9)
            border.width: 3
            border.color: index === 0 ? root.accent : Qt.rgba(1, 1, 1, 0.36)
            opacity: Math.max(
                0,
                Math.min(
                    1,
                    (root.frameProgress - index * 0.18) * 2
                )
            )
            y: 250 + (1 - opacity) * 70
            Text {
                x: 42
                y: 52
                width: parent.width - 84
                text: entry.label_ar
                color: index === 0 ? root.accent : root.fg
                font.family: graphicsSpec.design.font_family
                font.pixelSize: 48
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignRight
                layoutDirection: Qt.RightToLeft
            }
            Text {
                x: 42
                y: 160
                width: parent.width - 84
                text: entry.secondary_ar
                color: Qt.rgba(1, 1, 1, 0.68)
                font.family: graphicsSpec.design.font_family
                font.pixelSize: 30
                horizontalAlignment: Text.AlignRight
                wrapMode: Text.WordWrap
                layoutDirection: Qt.RightToLeft
            }
            Text {
                x: 42
                y: 300
                width: parent.width - 84
                text: entry.value_ar
                color: root.fg
                font.family: graphicsSpec.design.font_family
                font.pixelSize: 35
                horizontalAlignment: Text.AlignRight
                wrapMode: Text.WordWrap
                layoutDirection: Qt.RightToLeft
            }
        }
    }
}
