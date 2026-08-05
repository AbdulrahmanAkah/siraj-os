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
    readonly property var points: graphicsSpec.items

    Image {
        anchors.fill: parent
        source: graphicsSpec.background.image_url
        visible: graphicsSpec.background.mode === "IMAGE_WITH_OVERLAY"
        fillMode: Image.PreserveAspectCrop
        opacity: 0.62
    }
    Rectangle {
        anchors.fill: parent
        color: graphicsSpec.design.background_hex
        opacity: graphicsSpec.background.overlay_opacity
    }
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
    Canvas {
        id: routeCanvas
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.lineCap = "round"
            ctx.lineJoin = "round"
            ctx.lineWidth = 9
            ctx.strokeStyle = accent
            if (points.length < 2)
                return
            var segmentProgress = root.frameProgress * (points.length - 1)
            var complete = Math.floor(segmentProgress)
            var partial = segmentProgress - complete
            ctx.beginPath()
            var sx = safe + points[0].x * (root.width - safe * 2)
            var sy = 220 + points[0].y * 690
            ctx.moveTo(sx, sy)
            for (var i = 1; i <= complete && i < points.length; ++i) {
                ctx.lineTo(
                    safe + points[i].x * (root.width - safe * 2),
                    220 + points[i].y * 690
                )
            }
            if (complete + 1 < points.length) {
                var a = points[complete]
                var b = points[complete + 1]
                ctx.lineTo(
                    safe + (a.x + (b.x - a.x) * partial) * (root.width - safe * 2),
                    220 + (a.y + (b.y - a.y) * partial) * 690
                )
            }
            ctx.stroke()
        }
        Connections {
            target: root
            function onFrameProgressChanged() {
                routeCanvas.requestPaint()
            }
        }
    }
    Repeater {
        model: points
        delegate: Item {
            required property var modelData
            required property int index
            x: safe + modelData.x * (root.width - safe * 2) - 90
            y: 220 + modelData.y * 690 - 50
            width: 180
            height: 130
            opacity: root.frameProgress >= index / Math.max(1, points.length - 1)
                     ? 1 : 0
            Rectangle {
                anchors.horizontalCenter: parent.horizontalCenter
                width: 30
                height: 30
                radius: 15
                color: root.accent
                border.width: 5
                border.color: root.fg
            }
            Text {
                y: 42
                width: parent.width
                text: modelData.label_ar
                color: root.fg
                font.family: graphicsSpec.design.font_family
                font.pixelSize: 28
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                layoutDirection: Qt.RightToLeft
            }
        }
    }
}
