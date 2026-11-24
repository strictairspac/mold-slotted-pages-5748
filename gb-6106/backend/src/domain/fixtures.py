FIXTURES = [
    {
        "code": "GM-C4-P07",
        "title": "C4 三号模具清班",
        "description": "三条压模履历入页，撤销传感器空跑并追加裂纹复测备注，核对槽号稳定。",
        "payload": {
            "operations": [
                {"op": "insert", "key": "GM-071", "note": "06:50 C4#03 首件合格；模温 184C"},
                {"op": "insert", "key": "GM-072", "note": "06:52 C4#03 空跑，传感器抖动"},
                {"op": "insert", "key": "GM-073", "note": "06:57 C4#03 更换下压块，待复确认"},
                {"op": "delete", "key": "GM-072"},
                {"op": "update", "key": "GM-071", "note": "06:50 C4#03 首件合格；模温 184C。08:15 裂纹复测通过，主管盖印。"},
                {"op": "insert", "key": "GM-074", "note": "08:20 模具清班"},
                {"op": "compact"},
            ]
        },
    },
    {
        "code": "GM-D2-P14",
        "title": "D2 小页装不下的复测单",
        "description": "同编号重复入页被拒；短备注改写后人工压实并核对回收字节。",
        "payload": {
            "operations": [
                {"op": "insert", "key": "GM-141", "note": "10:12 D2 返修补记，更换上压块并补拍划痕近照"},
                {"op": "insert", "key": "GM-141", "note": "误录的同号履历"},
                {"op": "update", "key": "GM-141", "note": "D2 已换块"},
                {"op": "compact"},
            ]
        },
    },
]
