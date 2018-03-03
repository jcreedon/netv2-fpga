#!/usr/bin/env python3
import sys
import os

from litex.gen import *
from litex.gen.genlib.resetsync import AsyncResetSynchronizer

from litex.build.generic_platform import *
from litex.build.xilinx import XilinxPlatform

from litex.soc.integration.soc_core import mem_decoder
from litex.soc.integration.soc_sdram import *
from litex.soc.integration.builder import *
from litex.soc.integration.cpu_interface import get_csr_header
from litex.soc.cores import dna, xadc
from litex.soc.cores.frequency_meter import FrequencyMeter

from litedram.modules import MT41J128M16
from litedram.phy import a7ddrphy
from litedram.core import ControllerSettings

from litepcie.phy.s7pciephy import S7PCIEPHY
from litepcie.core import LitePCIeEndpoint, LitePCIeMSI
from litepcie.frontend.dma import LitePCIeDMA
from litepcie.frontend.wishbone import LitePCIeWishboneBridge

from litevideo.input import HDMIIn
from litevideo.output import VideoOut
from litevideo.output.hdmi.s7 import S7HDMIOutEncoderSerializer, S7HDMIOutPHY

from gateware.dma import DMAWriter, DMAReader, DMAControl

from litedram.frontend.bist import LiteDRAMBISTGenerator
from litedram.frontend.bist import LiteDRAMBISTChecker

from litevideo.output import TimingDelay
from litevideo.output.core import VideoOutCore
from litevideo.csc.ycbcr2rgb import YCbCr2RGB
from litevideo.csc.ycbcr422to444 import YCbCr422to444
from litevideo.output.hdmi.encoder import Encoder

_io = [
    ("clk50", 0, Pins("J19"), IOStandard("LVCMOS33")),

    ("user_led", 0, Pins("M21"), IOStandard("LVCMOS33")),
    ("user_led", 1, Pins("N20"), IOStandard("LVCMOS33")),
    ("user_led", 2, Pins("L21"), IOStandard("LVCMOS33")),

    ("serial", 0,
        Subsignal("tx", Pins("E14")),
        Subsignal("rx", Pins("E13")),
        IOStandard("LVCMOS33"),
    ),

    ("serial", 1,
        Subsignal("tx", Pins("B18")), # hax 8
        Subsignal("rx", Pins("A18")), # hax 14
        IOStandard("LVCMOS33")
    ),

    ("ddram", 0,
        Subsignal("a", Pins(
            "U6 V4 W5 V5 AA1 Y2 AB1 AB3",
			"AB2 Y3 W6 Y1 V2 AA3"
            ),
            IOStandard("SSTL15")),
        Subsignal("ba", Pins("U5 W4 V7"), IOStandard("SSTL15")),
        Subsignal("ras_n", Pins("Y9"), IOStandard("SSTL15")),
        Subsignal("cas_n", Pins("Y7"), IOStandard("SSTL15")),
        Subsignal("we_n", Pins("V8"), IOStandard("SSTL15")),
        Subsignal("dm", Pins("G1 H4 M5 L3"), IOStandard("SSTL15")),
        Subsignal("dq", Pins(
            "C2 F1 B1 F3 A1 D2 B2 E2 "
            "J5 H3 K1 H2 J1 G2 H5 G3 "
            "N2 M6 P1 N5 P2 N4 R1 P6 "
            "K3 M2 K4 M3 J6 L5 J4 K6 "
            ),
            IOStandard("SSTL15"),
            Misc("IN_TERM=UNTUNED_SPLIT_50")),
        Subsignal("dqs_p", Pins("E1 K2 P5 M1"), IOStandard("DIFF_SSTL15")),
        Subsignal("dqs_n", Pins("D1 J2 P4 L1"), IOStandard("DIFF_SSTL15")),
        Subsignal("clk_p", Pins("R3"), IOStandard("DIFF_SSTL15")),
        Subsignal("clk_n", Pins("R2"), IOStandard("DIFF_SSTL15")),
        Subsignal("cke", Pins("Y8"), IOStandard("SSTL15")),
        Subsignal("odt", Pins("W9"), IOStandard("SSTL15")),
        Subsignal("reset_n", Pins("AB5"), IOStandard("LVCMOS15")),
        Subsignal("cs_n", Pins("V9"), IOStandard("SSTL15")),
        Misc("SLEW=FAST"),
    ),

    ("pcie_x1", 0,
        Subsignal("rst_n", Pins("E18"), IOStandard("LVCMOS33")),
        Subsignal("clk_p", Pins("F10")),
        Subsignal("clk_n", Pins("E10")),
        Subsignal("rx_p", Pins("D11")),
        Subsignal("rx_n", Pins("C11")),
        Subsignal("tx_p", Pins("D5")),
        Subsignal("tx_n", Pins("C5"))
    ),

    ("pcie_x2", 0,
        Subsignal("rst_n", Pins("E18"), IOStandard("LVCMOS33")),
        Subsignal("clk_p", Pins("F10")),
        Subsignal("clk_n", Pins("E10")),
        Subsignal("rx_p", Pins("D11 B10")),
        Subsignal("rx_n", Pins("C11 A10")),
        Subsignal("tx_p", Pins("D5 B6")),
        Subsignal("tx_n", Pins("C5 A6"))
    ),

    ("pcie_x4", 0,
        Subsignal("rst_n", Pins("E18"), IOStandard("LVCMOS33")),
        Subsignal("clk_p", Pins("F10")),
        Subsignal("clk_n", Pins("E10")),
        Subsignal("rx_p", Pins("D11 B10 D9 B8")),
        Subsignal("rx_n", Pins("C11 A10 C9 A8")),
        Subsignal("tx_p", Pins("D5 B6 D7 B4")),
        Subsignal("tx_n", Pins("C5 A6 C7 A4"))
    ),

    ("hdmi_in", 0,
        Subsignal("clk_p", Pins("L19"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("clk_n", Pins("L20"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data0_p", Pins("K21"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data0_n", Pins("K22"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data1_p", Pins("J20"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data1_n", Pins("J21"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data2_p", Pins("J22"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data2_n", Pins("H22"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("scl", Pins("T18"), IOStandard("LVCMOS33")),
        Subsignal("sda", Pins("V18"), IOStandard("LVCMOS33")),
    ),

    ("hdmi_in", 1,
        Subsignal("clk_p", Pins("Y18"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("clk_n", Pins("Y19"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data0_p", Pins("AA18"), IOStandard("TMDS_33")),
        Subsignal("data0_n", Pins("AB18"), IOStandard("TMDS_33")),
        Subsignal("data1_p", Pins("AA19"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data1_n", Pins("AB20"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data2_p", Pins("AB21"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data2_n", Pins("AB22"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("scl", Pins("W17"), IOStandard("LVCMOS33"), Inverted()),
        Subsignal("sda", Pins("R17"), IOStandard("LVCMOS33")),
    ),

    ("hdmi_out", 0,
        Subsignal("clk_p", Pins("W19"), Inverted(), IOStandard("TMDS_33")),
        Subsignal("clk_n", Pins("W20"), Inverted(), IOStandard("TMDS_33")),
        Subsignal("data0_p", Pins("W21"), IOStandard("TMDS_33")),
        Subsignal("data0_n", Pins("W22"), IOStandard("TMDS_33")),
        Subsignal("data1_p", Pins("U20"), IOStandard("TMDS_33")),
        Subsignal("data1_n", Pins("V20"), IOStandard("TMDS_33")),
        Subsignal("data2_p", Pins("T21"), IOStandard("TMDS_33")),
        Subsignal("data2_n", Pins("U21"), IOStandard("TMDS_33"))
    ),

    ("hdmi_out", 1,
        Subsignal("clk_p", Pins("G21"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("clk_n", Pins("G22"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data0_p", Pins("E22"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data0_n", Pins("D22"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data1_p", Pins("C22"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data1_n", Pins("B22"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data2_p", Pins("B21"), IOStandard("TMDS_33"), Inverted()),
        Subsignal("data2_n", Pins("A21"), IOStandard("TMDS_33"), Inverted()),
    ),

    ("hdmi_sda_over_up", 0, Pins("G20"), IOStandard("LVCMOS33")),
    ("hdmi_sda_over_dn", 0, Pins("F20"), IOStandard("LVCMOS33")), # must be mutex with the above

    ("hdmi_rx0_forceunplug", 0, Pins("M22"), IOStandard("LVCMOS33")), # forces an HPD on the RX0/TX0 path
    ("hdmi_rx0_forceplug", 0, Pins("N22"), IOStandard("LVCMOS33")),   # this needs to be mutex with the above

    ("hdmi_tx1_hpd_n", 0, Pins("U18"), IOStandard("LVCMOS33")),  # this is the internal hdmi-D port

    ("hdmi_tx1_cec", 0, Pins("P17"), IOStandard("LVCMOS33")),  # tx1/rx1 path
    ("hdmi_tx0_cec", 0, Pins("P20"), IOStandard("LVCMOS33")),  # tx0/rx0 path

    ("hdmi_ov0_cec", 0, Pins("P19"), IOStandard("LVCMOS33")),  # dedicated to the overlay input
    ("hdmi_ov0_hpd_n", 0, Pins("V17"), IOStandard("LVCMOS33")), # if the overlay input is plugged in

]


class Platform(XilinxPlatform):
    def __init__(self, toolchain="vivado", programmer="vivado"):
        XilinxPlatform.__init__(self, "xc7a35t-fgg484-2", _io,
                                toolchain=toolchain)

        self.add_platform_command(
            "set_property CONFIG_VOLTAGE 3.3 [current_design]")
        self.add_platform_command(
            "set_property CFGBVS VCCO [current_design]")
        self.add_platform_command(
            "set_property BITSTREAM.CONFIG.CONFIGRATE 22 [current_design]")
        self.add_platform_command(
            "set_property BITSTREAM.CONFIG.SPI_BUSWIDTH 1 [current_design]")
        self.toolchain.bitstream_commands = [
            "set_property CONFIG_VOLTAGE 1.5 [current_design]",
            "set_property CFGBVS GND [current_design]",
            "set_property BITSTREAM.CONFIG.CONFIGRATE 22 [current_design]",
            "set_property BITSTREAM.CONFIG.SPI_BUSWIDTH 1 [current_design]",
        ]
        self.toolchain.additional_commands = \
            ["write_cfgmem -verbose -force -format bin -interface spix1 -size 64 "
             "-loadbit \"up 0x0 {build_name}.bit\" -file {build_name}.bin"]
        self.programmer = programmer

        self.add_platform_command("""
create_clock -name pcie_phy_clk -period 10.0 [get_pins {{pcie_phy/pcie_support_i/pcie_i/inst/inst/gt_top_i/pipe_wrapper_i/pipe_lane[0].gt_wrapper_i/gtp_channel.gtpe2_channel_i/TXOUTCLK}}]
""")

    def create_programmer(self):
        if self.programmer == "vivado":
            return VivadoProgrammer(flash_part="n25q128-3.3v-spi-x1_x2_x4")
        else:
            raise ValueError("{} programmer is not supported"
                             .format(self.programmer))

    def do_finalize(self, fragment):
        XilinxPlatform.do_finalize(self, fragment)


def csr_map_update(csr_map, csr_peripherals):
    csr_map.update(dict((n, v)
        for v, n in enumerate(csr_peripherals, start=max(csr_map.values()) + 1)))


def period_ns(freq):
    return 1e9/freq


class CRG(Module):
    def __init__(self, platform):
        self.clock_domains.cd_sys = ClockDomain()
        self.clock_domains.cd_sys4x = ClockDomain(reset_less=True)
        self.clock_domains.cd_sys4x_dqs = ClockDomain(reset_less=True)
        self.clock_domains.cd_clk200 = ClockDomain()
        self.clock_domains.cd_clk100 = ClockDomain()

        clk50 = platform.request("clk50")
        rst = Signal()

        pll_locked = Signal()
        pll_fb = Signal()
        self.pll_sys = Signal()
        pll_sys4x = Signal()
        pll_sys4x_dqs = Signal()
        pll_clk200 = Signal()
        self.specials += [
            Instance("PLLE2_BASE",
                     p_STARTUP_WAIT="FALSE", o_LOCKED=pll_locked,

                     # VCO @ 1600 MHz
                     p_REF_JITTER1=0.01, p_CLKIN1_PERIOD=20.0,
                     p_CLKFBOUT_MULT=32, p_DIVCLK_DIVIDE=1,
                     i_CLKIN1=clk50, i_CLKFBIN=pll_fb, o_CLKFBOUT=pll_fb,

                     # 100 MHz
                     p_CLKOUT0_DIVIDE=16, p_CLKOUT0_PHASE=0.0,
                     o_CLKOUT0=self.pll_sys,

                     # 400 MHz
                     p_CLKOUT1_DIVIDE=4, p_CLKOUT1_PHASE=0.0,
                     o_CLKOUT1=pll_sys4x,

                     # 400 MHz dqs
                     p_CLKOUT2_DIVIDE=4, p_CLKOUT2_PHASE=90.0,
                     o_CLKOUT2=pll_sys4x_dqs,

                     # 200 MHz
                     p_CLKOUT3_DIVIDE=8, p_CLKOUT3_PHASE=0.0,
                     o_CLKOUT3=pll_clk200
            ),
            Instance("BUFG", i_I=self.pll_sys, o_O=self.cd_sys.clk),
            Instance("BUFG", i_I=self.pll_sys, o_O=self.cd_clk100.clk),
            Instance("BUFG", i_I=pll_clk200, o_O=self.cd_clk200.clk),
            Instance("BUFG", i_I=pll_sys4x, o_O=self.cd_sys4x.clk),
            Instance("BUFG", i_I=pll_sys4x_dqs, o_O=self.cd_sys4x_dqs.clk),
            AsyncResetSynchronizer(self.cd_sys, ~pll_locked | rst),
            AsyncResetSynchronizer(self.cd_clk200, ~pll_locked | rst),
            AsyncResetSynchronizer(self.cd_clk100, ~pll_locked | rst)
        ]

        reset_counter = Signal(4, reset=15)
        ic_reset = Signal(reset=1)
        self.sync.clk200 += \
            If(reset_counter != 0,
                reset_counter.eq(reset_counter - 1)
            ).Else(
                ic_reset.eq(0)
            )
        self.specials += Instance("IDELAYCTRL", i_REFCLK=ClockSignal("clk200"), i_RST=ic_reset)


class BaseSoC(SoCSDRAM):
    csr_peripherals = {
        "ddrphy",
        "dna",
        "xadc",
    }
    csr_map_update(SoCSDRAM.csr_map, csr_peripherals)

    def __init__(self, platform, **kwargs):
        clk_freq = int(100e6)
        SoCSDRAM.__init__(self, platform, clk_freq,
            integrated_rom_size=0x6000,
            integrated_sram_size=0x4000,
            #shadow_base=0x00000000,
            ident="NeTV2 LiteX Base SoC",
            reserve_nmi_interrupt=False,
            **kwargs)

        self.submodules.crg = CRG(platform)
        self.submodules.dna = dna.DNA()
        self.submodules.xadc = xadc.XADC()

        self.crg.cd_sys.clk.attr.add("keep")
        platform.add_period_constraint(self.crg.cd_sys.clk, period_ns(100e6))

        # sdram
        self.submodules.ddrphy = a7ddrphy.A7DDRPHY(platform.request("ddram"))
        sdram_module = MT41J128M16(self.clk_freq, "1:4")
        self.add_constant("READ_LEVELING_BITSLIP", 3)
        self.add_constant("READ_LEVELING_DELAY", 14)
        self.register_sdram(self.ddrphy,
                            sdram_module.geom_settings,
                            sdram_module.timing_settings,
                            controller_settings=ControllerSettings(with_bandwidth=True,
                                                                   cmd_buffer_depth=8,
                                                                   with_refresh=False))

        # common led
        self.sys_led = Signal()
        self.pcie_led = Signal()
        self.comb += platform.request("user_led", 0).eq(self.sys_led ^ self.pcie_led)

        # sys led
        sys_counter = Signal(32)
        self.sync += sys_counter.eq(sys_counter + 1)
        self.comb += self.sys_led.eq(sys_counter[26])


class PCIeSoC(BaseSoC):
    csr_map = {
        "pcie_phy":        20,
        "dma":             21,
        "msi":             22,
        "dram_dma_writer": 23,
        "dram_dma_reader": 24
    }
    csr_map.update(BaseSoC.csr_map)

    BaseSoC.mem_map["csr"] = 0x00000000
    BaseSoC.mem_map["rom"] = 0x20000000

    def __init__(self, platform, **kwargs):
        BaseSoC.__init__(self, platform, csr_data_width=32, **kwargs)

        # pcie phy
        self.submodules.pcie_phy = S7PCIEPHY(platform, platform.request("pcie_x2"))
        platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.pcie_phy.cd_pcie.clk)

        # pcie endpoint
        self.submodules.pcie_endpoint = LitePCIeEndpoint(self.pcie_phy, with_reordering=True)

        # pcie wishbone bridge
        self.submodules.pcie_wishbone = LitePCIeWishboneBridge(self.pcie_endpoint, lambda a: 1)
        self.add_wb_master(self.pcie_wishbone.wishbone)

        # pcie dma
        self.submodules.dma = LitePCIeDMA(self.pcie_phy, self.pcie_endpoint, with_loopback=True)
        dram_dma_writer = DMAWriter(self.sdram.crossbar.get_port(mode="write", dw=64))
        dram_dma_reader = DMAReader(self.sdram.crossbar.get_port(mode="read", dw=64))
        self.submodules += dram_dma_writer, dram_dma_reader
        self.submodules.dram_dma_writer = DMAControl(dram_dma_writer)
        self.submodules.dram_dma_reader = DMAControl(dram_dma_reader)
        self.comb += [
            self.dma.source.connect(dram_dma_writer.sink),
            dram_dma_reader.source.connect(self.dma.sink)
        ]

        # pcie msi
        self.submodules.msi = LitePCIeMSI()
        self.comb += self.msi.source.connect(self.pcie_phy.msi)
        self.interrupts = {
            "DMA_WRITER":    self.dma.writer.irq,
            "DMA_READER":    self.dma.reader.irq
        }
        for i, (k, v) in enumerate(sorted(self.interrupts.items())):
            self.comb += self.msi.irqs[i].eq(v)
            self.add_constant(k + "_INTERRUPT", i)

        # pcie led
        pcie_counter = Signal(32)
        self.sync.pcie += pcie_counter.eq(pcie_counter + 1)
        self.comb += self.pcie_led.eq(pcie_counter[26])

    def generate_software_header(self):
        csr_header = get_csr_header(self.get_csr_regions(),
                                    self.get_constants(),
                                    with_access_functions=False)
        tools.write_to_file(os.path.join("software", "pcie", "kernel", "csr.h"), csr_header)

class VideoSoC(BaseSoC):
    csr_peripherals = {
        "hdmi_out0",
        "hdmi_in0",
        "hdmi_in0_freq",
        "hdmi_in0_edid_mem",
        "analyzer"
    }
    csr_map_update(BaseSoC.csr_map, csr_peripherals)

    interrupt_map = {
        "hdmi_in0": 3,
    }
    interrupt_map.update(BaseSoC.interrupt_map)

    def __init__(self, platform, *args, **kwargs):
        BaseSoC.__init__(self, platform, *args, **kwargs)

        # # #

        pix_freq = 148.50e6

        # hdmi in
        hdmi_in0_pads = platform.request("hdmi_in", 0)
        self.submodules.hdmi_in0_freq = FrequencyMeter(period=self.clk_freq)
        self.submodules.hdmi_in0 = HDMIIn(hdmi_in0_pads,
                                         self.sdram.crossbar.get_port(mode="write"),
                                         fifo_depth=512,
                                         device="xc7")
        self.comb += self.hdmi_in0_freq.clk.eq(self.hdmi_in0.clocking.cd_pix.clk)
        self.platform.add_period_constraint(self.hdmi_in0.clocking.cd_pix.clk, period_ns(1*pix_freq))
        self.platform.add_period_constraint(self.hdmi_in0.clocking.cd_pix1p25x.clk, period_ns(1.25*pix_freq))
        self.platform.add_period_constraint(self.hdmi_in0.clocking.cd_pix5x.clk, period_ns(5*pix_freq))

        self.platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.hdmi_in0.clocking.cd_pix.clk,
            self.hdmi_in0.clocking.cd_pix1p25x.clk,
            self.hdmi_in0.clocking.cd_pix5x.clk)

        # hdmi out
        hdmi_out0_dram_port = self.sdram.crossbar.get_port(mode="read", dw=16, cd="hdmi_out0_pix", reverse=True)
        self.submodules.hdmi_out0 = VideoOut(platform.device,
                                            platform.request("hdmi_out", 0),
                                            hdmi_out0_dram_port,
                                            "ycbcr422",
                                            fifo_depth=4096)

        self.platform.add_period_constraint(self.hdmi_out0.driver.clocking.cd_pix.clk, period_ns(1*pix_freq))
        self.platform.add_period_constraint(self.hdmi_out0.driver.clocking.cd_pix5x.clk, period_ns(5*pix_freq))

        self.platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.hdmi_out0.driver.clocking.cd_pix.clk,
            self.hdmi_out0.driver.clocking.cd_pix5x.clk)

        # hdmi over
        self.comb += [
            platform.request("hdmi_sda_over_up").eq(0),
            platform.request("hdmi_sda_over_dn").eq(0),
        ]

        # analyzer
        from litex.soc.cores.uart import UARTWishboneBridge
        from litescope import LiteScopeAnalyzer

        self.submodules.bridge = UARTWishboneBridge(
            platform.request("serial_litescope"), self.clk_freq, baudrate=115200)
        self.add_wb_master(self.bridge.wishbone)

        analyzer_signals = [
            self.hdmi_in0.data0_decod.valid_i,
            self.hdmi_in0.data0_decod.input,
            self.hdmi_in0.data1_decod.valid_i,
            self.hdmi_in0.data1_decod.input,
            self.hdmi_in0.data2_decod.valid_i,
            self.hdmi_in0.data2_decod.input,
        ]
        self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals, 2048, cd="hdmi_in0_pix", cd_ratio=2)

    def do_exit(self, vns):
        self.analyzer.export_csv(vns, "test/analyzer.csv")


class VideoOverlaySoC(BaseSoC):
    csr_peripherals = {
        "hdmi_out0",
        "hdmi_in0",
        "hdmi_in0_freq",
        "hdmi_in0_edid_mem",
        "hdmi_in1",
        "hdmi_in1_freq",
        "hdmi_in1_edid_mem",  
        "generator",
        "checker",
    }
    csr_map_update(BaseSoC.csr_map, csr_peripherals)

    interrupt_map = {
        "hdmi_in1": 3,
    }
    interrupt_map.update(BaseSoC.interrupt_map)

    def __init__(self, platform, *args, **kwargs):
        BaseSoC.__init__(self, platform, *args, **kwargs)

        # # #

        pix_freq = 148.50e6

        # bist
        generator_port = self.sdram.crossbar.get_port(cd="sys")  # mode="write"
        self.submodules.generator = LiteDRAMBISTGenerator(generator_port, random=True)

        checker_port = self.sdram.crossbar.get_port(cd="sys")  # mode="read"
        self.submodules.checker = LiteDRAMBISTChecker(checker_port, random=True)

        # hdmi in 0 (raw tmds)
        hdmi_in0_pads = platform.request("hdmi_in", 0)
        self.submodules.hdmi_in0_freq = FrequencyMeter(period=self.clk_freq)
        self.submodules.hdmi_in0 = HDMIIn(hdmi_in0_pads, device="xc7", split_mmcm=True)
        self.comb += self.hdmi_in0_freq.clk.eq(self.hdmi_in0.clocking.cd_pix.clk)
        platform.add_period_constraint(self.hdmi_in0.clocking.cd_pix.clk, period_ns(1*pix_freq))
        platform.add_period_constraint(self.hdmi_in0.clocking.cd_pix_o.clk, period_ns(1*pix_freq))
        platform.add_period_constraint(self.hdmi_in0.clocking.cd_pix1p25x.clk, period_ns(1.25*pix_freq))
        platform.add_period_constraint(self.hdmi_in0.clocking.cd_pix5x.clk, period_ns(5*pix_freq))

        platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.hdmi_in0.clocking.cd_pix.clk,
            self.hdmi_in0.clocking.cd_pix_o.clk,
            self.hdmi_in0.clocking.cd_pix1p25x.clk,
            self.hdmi_in0.clocking.cd_pix5x.clk)

        hdmi_out0_pads = platform.request("hdmi_out", 0)
        self.submodules.hdmi_out0_clk_gen = S7HDMIOutEncoderSerializer(hdmi_out0_pads.clk_p, hdmi_out0_pads.clk_n, bypass_encoder=True)
        self.comb += self.hdmi_out0_clk_gen.data.eq(Signal(10, reset=0b0000011111))
        self.submodules.hdmi_out0_phy = S7HDMIOutPHY(hdmi_out0_pads, mode="raw")

        # hdmi over
        self.comb += [
            platform.request("hdmi_sda_over_up").eq(0),
            platform.request("hdmi_sda_over_dn").eq(0),
        ]

        platform.add_platform_command(
            "set_property CLOCK_DEDICATED_ROUTE FALSE [get_nets hdmi_in_ibufds/ob]")


        # hdmi in 1
        hdmi_in1_pads = platform.request("hdmi_in", 1)
        self.submodules.hdmi_in1_freq = FrequencyMeter(period=self.clk_freq)
        self.submodules.hdmi_in1 = HDMIIn(hdmi_in1_pads,
                                         self.sdram.crossbar.get_port(mode="write"),
                                         fifo_depth=512,
                                         device="xc7",
                                         split_mmcm=False)
        self.comb += self.hdmi_in1_freq.clk.eq(self.hdmi_in1.clocking.cd_pix.clk)
        platform.add_period_constraint(self.hdmi_in1.clocking.cd_pix.clk, period_ns(1*pix_freq))
        platform.add_period_constraint(self.hdmi_in1.clocking.cd_pix1p25x.clk, period_ns(1.25*pix_freq))
        platform.add_period_constraint(self.hdmi_in1.clocking.cd_pix5x.clk, period_ns(5*pix_freq))

        platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.hdmi_in1.clocking.cd_pix.clk,
            self.hdmi_in1.clocking.cd_pix1p25x.clk,
            self.hdmi_in1.clocking.cd_pix5x.clk)

        #  hdmi out 1 (overlay ycbcr422)
        #dma_reader = DMAReader(self.sdram.crossbar.get_port(mode="read", cd="pix_o"), dw=16)
        #dma_reader = ClockDomainsRenamer("pix_o")(dma_reader)
        #self.submodules += dma_reader
        #self.submodules.dma_reader = ClockDomainsRenamer({"pix" : "pix_o"})(DMAControl(dma_reader))


        out_dram_port = self.sdram.crossbar.get_port(mode="read", cd="pix_o", dw=16)
        genlock_from_input = Signal()
        self.submodules.hdmi_out0 = VideoOutCore(out_dram_port, mode="ycbcr422", fifo_depth=512, genlock=True, genlock_signal=genlock_from_input)
        # we should need to access the .core signals as a CSR, right?
        vsync = Signal()
        vsync_r = Signal()
        new_frame = Signal()
        self.comb += vsync.eq(self.hdmi_in0.syncpol.vsync)
        self.comb += new_frame.eq(vsync & ~vsync_r)  # pulses high on new frame
        self.sync.pix_o += vsync_r.eq(vsync)
        self.comb += genlock_from_input.eq(new_frame)

        ycbcr422to444 = ClockDomainsRenamer("pix_o")(YCbCr422to444())
        ycbcr2rgb = ClockDomainsRenamer("pix_o")(YCbCr2RGB())
        timing_delay = TimingDelay(ycbcr422to444.latency + ycbcr2rgb.latency)
        timing_delay = ClockDomainsRenamer(out_dram_port.cd)(timing_delay)
        self.submodules += ycbcr422to444, ycbcr2rgb, timing_delay

        # data / control
        de_r = Signal()
        core_source_valid_d = Signal()
        core_source_data_d = Signal(16)
        sync_cd = getattr(self.sync, out_dram_port.cd)
        sync_cd += [
            de_r.eq(self.hdmi_out0.source.de),
            core_source_valid_d.eq(self.hdmi_out0.source.valid),
            core_source_data_d.eq(self.hdmi_out0.source.data),
        ]

        self.comb += [
            self.hdmi_out0.source.ready.eq(1),  # always ready, no flow control
            ycbcr422to444.reset.eq(self.hdmi_out0.source.de & ~de_r),
            ycbcr422to444.sink.valid.eq(core_source_valid_d),
            ycbcr422to444.sink.y.eq(core_source_data_d[:8]),
            ycbcr422to444.sink.cb_cr.eq(core_source_data_d[8:]),

            ycbcr422to444.source.connect(ycbcr2rgb.sink),

#            ycbcr2rgb.source.connect(driver.sink)
        ]
        # timing
        self.comb += [
            timing_delay.sink.de.eq(self.hdmi_out0.source.de),
            timing_delay.sink.vsync.eq(self.hdmi_out0.source.vsync),
            timing_delay.sink.hsync.eq(self.hdmi_out0.source.hsync),

#            driver.sink.de.eq(timing_delay.source.de),
#            driver.sink.vsync.eq(timing_delay.source.vsync),
#            driver.sink.hsync.eq(timing_delay.source.hsync)
        ]

        self.submodules.encoder_red = encoder_red = ClockDomainsRenamer("pix_o")(Encoder())
        self.submodules.encoder_grn = encoder_grn = ClockDomainsRenamer("pix_o")(Encoder())
        self.submodules.encoder_blu = encoder_blu = ClockDomainsRenamer("pix_o")(Encoder())

        red_c = Signal(2)
        grn_c = Signal(2)
        blu_c = Signal(2)
        self.sync.pix_o += [
            red_c.eq(self.hdmi_in0.data2_decod.output.c),
            grn_c.eq(self.hdmi_in0.data1_decod.output.c),
            blu_c.eq(self.hdmi_in0.data0_decod.output.c)
        ]
        self.comb += [
            ycbcr2rgb.source.ready.eq(1),

            encoder_red.d.eq(ycbcr2rgb.source.r),
            encoder_red.de.eq(1),
            encoder_red.c.eq(red_c),

            encoder_grn.d.eq(ycbcr2rgb.source.g),
            encoder_grn.de.eq(1),
            encoder_grn.c.eq(grn_c),

            encoder_blu.d.eq(ycbcr2rgb.source.b),
            encoder_blu.de.eq(1),
            encoder_blu.c.eq(blu_c),
        ]

        # TODO: hdmi out 1 to hdmi out 0 injection
        #self.comb += [
            #ycbcr2rgb.source.valid
            #ycbcr2rgb.source.r
            #ycbcr2rgb.source.g
            #ycbcr2rgb.source.b
        #]

        # hdmi in to hdmi out
        c0_pix_o = Signal(10)
        c1_pix_o = Signal(10)
        c2_pix_o = Signal(10)
        self.sync.pix_o += [  # extra delay to absorb cross-domain jitter & routing
            c0_pix_o.eq(self.hdmi_in0.syncpol.c0),
            c1_pix_o.eq(self.hdmi_in0.syncpol.c1),
            c2_pix_o.eq(self.hdmi_in0.syncpol.c2)
        ]

        self.sync.pix_o += [
            If( (self.hdmi_out0.timing.hcounter > 100) & (self.hdmi_out0.timing.hcounter < 400) &
                (self.hdmi_out0.timing.vcounter > 100) & (self.hdmi_out0.timing.vcounter < 400),
                    self.hdmi_out0_phy.sink.c0.eq(encoder_blu.out),
                    self.hdmi_out0_phy.sink.c1.eq(encoder_grn.out),
                    self.hdmi_out0_phy.sink.c2.eq(encoder_red.out),
                ).Else(
                    self.hdmi_out0_phy.sink.c0.eq(c0_pix_o),
                    self.hdmi_out0_phy.sink.c1.eq(c1_pix_o),
                    self.hdmi_out0_phy.sink.c2.eq(c2_pix_o),
            )
        ]

"""
        # litescope
        litescope_serial = platform.request("serial", 1)
        litescope_bus = Signal(128)
        litescope_i = Signal(16)
        litescope_o = Signal(16)
        self.specials += [
            Instance("litescope",
                i_clock=ClockSignal(),
                i_reset=ResetSignal(),
                i_serial_rx=litescope_serial.rx,
                o_serial_tx=litescope_serial.tx,
                i_bus=litescope_bus,
                i_i=litescope_i,
                o_o=litescope_o
            )
        ]
        platform.add_source(os.path.join("litescope", "litescope.v"))

        # litescope test
        self.comb += [
            litescope_bus.eq(0x12345678ABCFEF),
            platform.request("user_led", 1).eq(litescope_o[0]),
            platform.request("user_led", 2).eq(litescope_o[1]),
            litescope_i.eq(0x5AA5)
        ]
"""




class VideoRawDMALoopbackSoC(BaseSoC):
    csr_peripherals = {
        "hdmi_out0",
        "hdmi_in0",
        "hdmi_in0_freq",
        "hdmi_in0_edid_mem",
        "dma_writer",
        "dma_reader"
    }
    csr_map_update(BaseSoC.csr_map, csr_peripherals)

    def __init__(self, platform, *args, **kwargs):
        BaseSoC.__init__(self, platform, *args, **kwargs)

        # # #

        pix_freq = 148.50e6

        # hdmi in
        hdmi_in0_pads = platform.request("hdmi_in", 0)
        self.submodules.hdmi_in0_freq = FrequencyMeter(period=self.clk_freq)
        self.submodules.hdmi_in0 = HDMIIn(hdmi_in0_pads, device="xc7")
        self.comb += self.hdmi_in0_freq.clk.eq(self.hdmi_in0.clocking.cd_pix.clk)
        self.platform.add_period_constraint(self.hdmi_in0.clocking.cd_pix.clk, period_ns(1*pix_freq))
        self.platform.add_period_constraint(self.hdmi_in0.clocking.cd_pix1p25x.clk, period_ns(1.25*pix_freq))
        self.platform.add_period_constraint(self.hdmi_in0.clocking.cd_pix5x.clk, period_ns(5*pix_freq))

        self.platform.add_false_path_constraints(
            self.crg.cd_sys.clk,
            self.hdmi_in0.clocking.cd_pix.clk,
            self.hdmi_in0.clocking.cd_pix1p25x.clk,
            self.hdmi_in0.clocking.cd_pix5x.clk)

        # hdmi out
        hdmi_out0_pads = platform.request("hdmi_out", 0)
        self.submodules.hdmi_out0_clk_gen = S7HDMIOutEncoderSerializer(hdmi_out0_pads.clk_p, hdmi_out0_pads.clk_n, bypass_encoder=True)
        self.comb += self.hdmi_out0_clk_gen.data.eq(Signal(10, reset=0b0000011111))
        self.submodules.hdmi_out0_phy = S7HDMIOutPHY(hdmi_out0_pads, mode="raw")

        # hdmi over
        self.comb += [
            platform.request("hdmi_sda_over_up").eq(0),
            platform.request("hdmi_sda_over_dn").eq(0),
        ]

        # dram dmas
        dma_writer = DMAWriter(self.sdram.crossbar.get_port(mode="write", cd="pix"))
        dma_writer = ClockDomainsRenamer("pix")(dma_writer)
        dma_reader = DMAReader(self.sdram.crossbar.get_port(mode="read", cd="pix"))
        dma_reader = ClockDomainsRenamer("pix")(dma_reader)
        self.submodules += dma_writer, dma_reader
        self.submodules.dma_writer = DMAControl(dma_writer)
        self.submodules.dma_reader = DMAControl(dma_reader)

        # hdmi in dma
        self.comb += [
            dma_writer.sink.valid.eq(1),
            #dma_writer.sink.ready # overflows monitored with litescope
            dma_writer.sink.data[0:10].eq(self.hdmi_in0.syncpol.c0),
            dma_writer.sink.data[10:20].eq(self.hdmi_in0.syncpol.c1),
            dma_writer.sink.data[20:30].eq(self.hdmi_in0.syncpol.c2),
        ]


        # hdmi out dma
        self.comb += [
            #dma_reader.source.valid # underflow monitored with litescope
            dma_reader.source.ready.eq(1),
            self.hdmi_out0_phy.sink.c0.eq(dma_reader.source.data[0:10]),
            self.hdmi_out0_phy.sink.c1.eq(dma_reader.source.data[10:20]),
            self.hdmi_out0_phy.sink.c2.eq(dma_reader.source.data[20:30]),
        ]

        # analyzer
        from litex.soc.cores.uart import UARTWishboneBridge
        from litescope import LiteScopeAnalyzer

        self.submodules.bridge = UARTWishboneBridge(
            platform.request("serial_litescope"), self.clk_freq, baudrate=3000000)
        self.add_wb_master(self.bridge.wishbone)

        analyzer_signals = [
            dma_writer.sink.ready,   # monitors dram writer overflows
            self.hdmi_in0.syncpol.c0,
            self.hdmi_in0.syncpol.c1,
            self.hdmi_in0.syncpol.c2,

            dma_reader.source.ready, # monitors dram read underflows
            self.hdmi_out0_phy.sink.c0,
            self.hdmi_out0_phy.sink.c1,
            self.hdmi_out0_phy.sink.c2
        ]
#        self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals, 256, cd="pix", cd_ratio=2)

    def do_exit(self, vns):
        self.analyzer.export_csv(vns, "test/analyzer.csv")


def main():
    platform = Platform()
    if len(sys.argv) < 2:
        print("missing target (base or pcie or video or video_overlay or video_raw_dma_loopback)")
        exit()
    if sys.argv[1] == "base":
        soc = BaseSoC(platform)
    elif sys.argv[1] == "pcie":
        soc = PCIeSoC(platform)
    elif sys.argv[1] == "video":
        soc = VideoSoC(platform)
    elif sys.argv[1] == "video_overlay":
        soc = VideoOverlaySoC(platform)
    elif sys.argv[1] == "video_raw_dma_loopback":
        soc = VideoRawDMALoopbackSoC(platform)
    builder = Builder(soc, output_dir="build", csr_csv="test/csr.csv")
    vns = builder.build()
    soc.do_exit(vns)

    if sys.argv[1] == "pcie":
        soc.generate_software_header()

if __name__ == "__main__":
    main()
