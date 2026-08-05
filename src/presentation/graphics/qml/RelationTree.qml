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
    readonly property var nodes: graphicsSpec.items

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
    }
    Canvas {
        id: lines
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.lineWidth = 4
            ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.38)
            for (var i = 0; i < nodes.length; ++i) {
                var child = nodes[i]
                if (!child.parent_item_id)
                    continue
                for (var j = 0; j < nodes.length; ++j) {
                    if (nodes[j].item_id !== child.parent_item_id)
                        continue
                    if (root.frameProgress < i / Math.max(1, nodes.length))
                        continue
                    ctx.beginPath()
                    ctx.moveTo(
                        safe + nodes[j].x * (root.width - safe * 2),
                        230 + nodes[j].y * 700
                    )
                    ctx.lineTo(
                        safe + child.x * (root.width - safe * 2),
                        230 + child.y * 700
                    )
                    ctx.stroke()
                }
            }
        }
        Connections {
            target: root
            function onFrameProgressChanged() { lines.requestPaint() }
        }
    }
    Repeater {
        model: nodes
        delegate: Rectangle {
            required property var modelData
            required property int index
            x: safe + modelData.x * (root.width - safe * 2) - width / 2
            y: 230 + modelData.y * 700 - height / 2
            width: 250
            height: 96
            radius: 18
            color: Qt.rgba(0.08, 0.07, 0.06, 0.88)
            border.width: 3
            border.color: root.accent
            opacity: Math.max(
                0,
                Math.min(
                    1,
                    (root.frameProgress - index / Math.max(1, nodes.length))
                    * nodes.length * 2.4
                )
            )
            scale: 0.92 + opacity * 0.08
            Text {
                anchors.fill: parent
                anchors.margins: 12
                text: modelData.label_ar
                color: root.fg
                font.family: graphicsSpec.design.font_family
                font.pixelSize: 29
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
                wrapMode: Text.WordWrap
            }
        }
    }
}
