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

    Image {
        anchors.fill: parent
        source: graphicsSpec.background.image_url
        visible: graphicsSpec.background.mode === "IMAGE_WITH_OVERLAY"
        fillMode: Image.PreserveAspectCrop
        opacity: 0.42
    }
    Rectangle {
        anchors.fill: parent
        color: graphicsSpec.design.background_hex
        opacity: graphicsSpec.background.overlay_opacity
    }
    Rectangle {
        x: safe
        y: 660
        width: parent.width - safe * 2
        height: 6
        radius: 3
        color: Qt.rgba(1, 1, 1, 0.18)
    }
    Rectangle {
        x: safe
        y: 660
        width: (parent.width - safe * 2) * Math.min(1, frameProgress * 1.12)
        height: 6
        radius: 3
        color: accent
    }
    Text {
        x: safe
        y: safe
        width: parent.width - safe * 2
        text: graphicsSpec.title_ar
        color: fg
        font.family: graphicsSpec.design.font_family
        font.pixelSize: 72
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignRight
        layoutDirection: Qt.RightToLeft
    }
    Text {
        x: safe
        y: safe + 104
        width: parent.width - safe * 2
        text: graphicsSpec.subtitle_ar
        color: Qt.rgba(1, 1, 1, 0.72)
        font.family: graphicsSpec.design.font_family
        font.pixelSize: 34
        horizontalAlignment: Text.AlignRight
        layoutDirection: Qt.RightToLeft
    }
    Repeater {
        model: entries
        delegate: Item {
            required property var modelData
            required property int index
            x: safe + (root.width - safe * 2) * modelData.x - 110
            y: 596
            width: 220
            height: 260
            opacity: Math.max(
                0,
                Math.min(
                    1,
                    (root.frameProgress - index / Math.max(1, entries.length))
                    * entries.length * 2.2
                )
            )
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 52
                width: 26
                height: 26
                radius: 13
                color: root.accent
                border.width: 5
                border.color: root.fg
            }
            Text {
                y: 100
                width: parent.width
                text: modelData.label_ar
                color: root.fg
                font.family: graphicsSpec.design.font_family
                font.pixelSize: 30
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                layoutDirection: Qt.RightToLeft
            }
            Text {
                y: 176
                width: parent.width
                text: modelData.value_ar
                color: root.accent
                font.family: graphicsSpec.design.font_family
                font.pixelSize: 25
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                layoutDirection: Qt.RightToLeft
            }
        }
    }
}
