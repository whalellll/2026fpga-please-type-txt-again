"""Refresh CPU75 delivery status from local source-bound receipts; no board access."""
import hashlib,json,re
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def main():
    root=Path(__file__).resolve().parents[1]
    base=root/'docs/validation/main75-release-20261028'
    state=read(base/'current-state.json')
    for name,h in state['receipts_sha256'].items():
        p=(base/name).resolve();assert p.is_relative_to(base.resolve()) and sha(p)==h,name
    software=read(base/'mouse/runtime.json')
    assert software['status']=='HOST_RV32_RUNTIME_INTEGRATION_PASS_NOT_BOARD' and software['source_stable']
    for name,h in software['source_sha256'].items():assert sha(root/name)==h,name
    from audit_main75_candidate import validate
    validate(root,base/'native-result.json',root/'artifacts/soc_top.sbit')
    launch=read(base/'mouse/launch.result.json')
    assert launch['status']=='BOARD_COMMAND_SPEC_PASS'
    sd=read(base/'mouse/sd-preparation.json')
    assert sd['status']=='CPU75_MOUSE_GUI_SD8_AND_18_REAL_LOADER_TESTS_PASS_NOT_MEDIA' and len(sd['tests'])==18
    assert sd['gui_sha256']==state['mouse_gui_sha256']
    begin='<!-- MAIN75_DELIVERY_SOURCE_BOUND_20261028_BEGIN -->';end='<!-- MAIN75_DELIVERY_SOURCE_BOUND_20261028_END -->'
    block=f'''{begin}
## CPU75 交付来源核对

状态：`{state['status']}`。源码 `{root.as_posix()}`；交付作业
`G:/fpga/build/main75-delivery-20261028-01`。native run 9302a6212eac40b08fae353321f31d1c，
位流 d2ab7f6d，CPU75/SYS49.5，原生517输入/46报告/49输出回读一致。
鼠标 GUI `{state['mouse_gui_sha256']}`；host/RV32 运行时及主循环、90格刷新检查通过，
板端 RAM 实际执行哈希/首帧/非暂停状态通过。实体选子/走子/应着确认：
`{state['board_mouse_confirmation']}`。SD8及18项真实加载器离线检查通过，尚未写入实体卡。

main已推送：`{state['main_pushed']}`；正式ZIP：`{state['formal_zip_created']}`；
交付完成：`{state['formal_delivery_complete']}`。G可用字节：`{state['workspace_free_bytes']}`；
H可用：`{state['archive_drive_available']}`，原始候选和证据保留。
真实板端鼠标命令/引擎/播报/重开/返回事务通过：`{state.get('real_mouse_transaction_validated',False)}`。
实现验证成功后按授权顺序推main回读，再封包、独立解包回归及最终SD直接启动；实体鼠标传输与HDMI确认仍单独待验。
NNUE10ms/图像30fps目标未达到，r05研究语音模型未晋升准确率，真实麦克风不在当前要求范围；
187项既有外部I/O覆盖缺口保留，不写Flash。证据详见docs/validation/main75-release-20261028/current-state.json。
{end}'''
    docs=[root/'docs/CPU_Frequency_Handoff.md']
    if root.parent==Path('G:/fpga'):
        docs += [root.parent/'HANDOFF.md',root.parent/'performance_soc_voice_hw/docs/CPU_Frequency_Handoff.md']
    for p in docs:
        text=p.read_text(encoding='utf-8-sig')
        if begin in text:
            assert text.count(begin)==text.count(end)==1
            text=re.sub(re.escape(begin)+r'[\s\S]*?'+re.escape(end),lambda _:block,text,count=1)
        else:text=block+'\n\n'+text
        p.write_text(text,encoding='utf8')
    print('CPU75_DELIVERY_SOURCE_BOUND_HANDOFF_REFRESHED_NO_BOARD_BUILD_OR_PUSH')

if __name__=='__main__':main()
