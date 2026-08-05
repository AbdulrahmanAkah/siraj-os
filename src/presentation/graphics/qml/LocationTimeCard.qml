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
    readonly property var entry: graphicsSpec.items[0]
    readonly property real reveal: Math.min(1, frameProgress * 1.55)

    Image {
        anchors.fill: parent
        source: graphicsSpec.background.image_url
        visible: graphicsSpec.background.mode === "IMAGE_WITH_OVERLAY"
        fillMode: Image.PreserveAspectCrop
        opacity: 0.65
        scale: 1.06 - root.frameProgress * 0.04
    }
    Rectangle {
        anchors.fill: parent
        color: graphicsSpec.design.background_hex
        opacity: graphicsSpec.background.overlay_opacity
    }
    Rectangle {
        x: safe
        y: 290
        width: 18
        height: 430 * reveal
        radius: 9
        color: accent
    }
    Text {
        x: safe + 72
        y: 300
        width: parent.width - safe * 2 - 72
        text: entry.label_ar
        color: fg
        font.family: graphicsSpec.design.font_family
        font.pixelSize: 96
        font.weight: Font.DemiBold
        opacity: reveal
        horizontalAlignment: Text.AlignRight
        layoutDirection: Qt.RightToLeft
    }
    Text {
        x: safe + 72
        y: 460
        width: parent.width - safe * 2 - 72
        text: entry.value_ar
        color: accent
        font.family: graphicsSpec.design.font_family
        font.pixelSize: 54
        font.weight: Font.DemiBold
        opacity: Math.max(0, Math.min(1, (frameProgress - 0.14) * 2.1))
        horizontalAlignment: Text.AlignRight
        layoutDirection: Qt.RightToLeft
    }
    Text {
        x: safe + 72
        y: 570
        width: parent.width - safe * 2 - 72
        text: entry.secondary_ar
        color: Qt.rgba(1, 1, 1, 0.74)
        font.family: graphicsSpec.design.font_family
        font.pixelSize: 36
        opacity: Math.max(0, Math.min(1, (frameProgress - 0.27) * 2.0))
        horizontalAlignment: Text.AlignRight
        wrapMode: Text.WordWrap
        layoutDirection: Qt.RightToLeft
    }
}
