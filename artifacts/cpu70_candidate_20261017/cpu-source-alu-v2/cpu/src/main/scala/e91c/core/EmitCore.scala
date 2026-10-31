package e91c.core

import e91c.frontend.PangoIdentityPad

object EmitCore extends App {
  val supportedProperties = Set("e91c.aluEntries", "e91c.memEntries",
    "e91c.fallbackSets", "e91c.fallbackHash", "e91c.rasDepth",
    "e91c.synthesis", "e91c.socProbes", "e91c.supervisor")
  val unknownProperties = sys.props.keys.filter(_.startsWith("e91c.")).toSet -- supportedProperties
  require(unknownProperties.isEmpty,
    s"Unsupported CPU properties: ${unknownProperties.toSeq.sorted.mkString(", ")}")
  Seq("e91c.fallbackHash", "e91c.synthesis", "e91c.socProbes", "e91c.supervisor").foreach { key =>
    require(sys.props.get(key).forall(value => value == "true" || value == "false"),
      s"$key must be true or false")
  }
  val target = args.headOption.getOrElse("generated/core")
  require(args.drop(1).forall(_ == "--synthesis"), "Only --synthesis is supported after the output directory")
  // PDS 2022.2 cannot parse immediate SVA statements. Omit verification-only
  // assertions from synthesis exports; simulation and unit tests retain them.
  if (args.drop(1).contains("--synthesis")) System.setProperty("e91c.synthesis","true")
  else System.clearProperty("e91c.synthesis")
  circt.stage.ChiselStage.emitSystemVerilogFile(
  new CoreTop, Array("--target-dir", target),
  Array("--disable-all-randomization", "--strip-debug-info", "--lowering-options=disallowLocalVariables"))
  // Keep the synthesis export self-contained. This implementation is part of
  // the canonical source and is bundled before the generated hashes are taken.
  if (sys.props.get("e91c.synthesis").contains("true")) {
    val rtlPath = java.nio.file.Paths.get(target, "CoreTop.sv")
    val rtlText = new String(java.nio.file.Files.readAllBytes(rtlPath),
      java.nio.charset.StandardCharsets.UTF_8)
    val declaration = ("(?m)^\\s*module\\s+" + PangoIdentityPad.moduleName + "\\b").r
    val instance = ("(?m)^\\s*" + PangoIdentityPad.moduleName +
      "\\s+[A-Za-z_][A-Za-z0-9_$]*\\s*\\(").r
    require(declaration.findFirstIn(rtlText).isEmpty,
      "The fresh export already defines PangoIdentityPad; refuse duplicate bundling")
    require(instance.findAllMatchIn(rtlText).length == 1,
      "Expected exactly one shared I-cache PangoIdentityPad instance")
    java.nio.file.Files.write(rtlPath,
      ("\n" + PangoIdentityPad.verilog).getBytes(java.nio.charset.StandardCharsets.UTF_8),
      java.nio.file.StandardOpenOption.APPEND)
  }
  // Keep the emitted design portable: readmemh paths resolve from this directory.
  val initTarget = java.nio.file.Paths.get(target, "scripts", "meminit")
  java.nio.file.Files.createDirectories(initTarget)
  Seq(1024, 2048, 4096).foreach { depth =>
    val name = s"zero_$depth.hex"
    java.nio.file.Files.copy(
    java.nio.file.Paths.get("scripts", "meminit", name), initTarget.resolve(name),
    java.nio.file.StandardCopyOption.REPLACE_EXISTING)
  }
  // Record the values actually consumed by elaboration, never a guessed list
  // of command-line defaults or a dump of potentially sensitive JVM settings.
  import e91c.config.Params
  val synthesis = sys.props.get("e91c.synthesis").contains("true")
  val socProbes = sys.props.get("e91c.socProbes").contains("true")
  val configuration = s"""{
    |  "schema_version": 1,
    |  "isa": "rv32ima_zicsr_zifencei",
    |  "supervisor": ${Params.ENABLE_SUPERVISOR},
    |  "architecture": {
    |    "aluEntries": ${Params.RS_ALU_SIZE},
    |    "memEntries": ${Params.RS_MEM_SIZE},
    |    "fallbackSets": ${Params.FALLBACK_SETS},
    |    "fallbackHash": ${Params.FALLBACK_HASH},
    |    "rasDepth": ${Params.RAS_DEPTH}
    |  },
    |  "cache": {
    |    "lineBytes": ${Params.CACHE_LINE_BYTES},
    |    "l1Sets": ${Params.L1_NSET},
    |    "iWays": ${Params.ICACHE_NWAY},
    |    "dWays": ${Params.DCACHE_NWAY},
    |    "l2Sets": ${Params.L2_NSET},
    |    "l2Ways": ${Params.L2_NWAY}
    |  },
    |  "mode": { "synthesis": $synthesis, "socProbes": $socProbes }
    |}
    |""".stripMargin
  java.nio.file.Files.write(java.nio.file.Paths.get(target, "emit-config.json"),
    configuration.getBytes(java.nio.charset.StandardCharsets.UTF_8))
}
