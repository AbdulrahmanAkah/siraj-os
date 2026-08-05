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
    readonly property var sourceItem: graphicsSpec.items[0]

    Rectangle {
        id: card
        x: safe + (1 - Math.min(1, frameProgress * 1.3)) * 160
        y: 190
        width: parent.width - safe * 2
        height: 700
        radius: 34
        color: Qt.rgba(0.08, 0.07, 0.06, 0.93)
        border.width: 3
        border.color: accent
        opacity: Math.min(1, frameProgress * 1.6)

        Rectangle {
            x: 0
            y: 0
            width: 16
            height: parent.height
            radius: 8
            color: accent
        }
        Text {
            x: 70
            y: 70
            width: parent.width - 140
            text: graphicsSpec.title_ar
            color: fg
            font.family: graphicsSpec.design.font_family
            font.pixelSize: 62
            font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignRight
            layoutDirection: Qt.RightToLeft
        }
        Text {
            x: 70
            y: 190
            width: parent.width - 140
            text: sourceItem.label_ar
            color: accent
            font.family: graphicsSpec.design.font_family
            font.pixelSize: 46
            font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignRight
            layoutDirection: Qt.RightToLeft
        }
        Text {
            x: 70
            y: 285
            width: parent.width - 140
            text: sourceItem.secondary_ar
            color: Qt.rgba(1, 1, 1, 0.72)
            font.family: graphicsSpec.design.font_family
            font.pixelSize: 32
            horizontalAlignment: Text.AlignRight
            layoutDirection: Qt.RightToLeft
        }
        Text {
            x: 100
            y: 410
            width: parent.width - 200
            text: sourceItem.value_ar
            color: fg
            font.family: graphicsSpec.design.font_family
            font.pixelSize: 38
            horizontalAlignment: Text.AlignRight
            verticalAlignment: Text.AlignVCenter
            wrapMode: Text.WordWrap
            layoutDirection: Qt.RightToLeft
        }
    }
}
