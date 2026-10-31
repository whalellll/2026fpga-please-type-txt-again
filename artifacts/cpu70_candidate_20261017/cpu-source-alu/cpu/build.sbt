ThisBuild / scalaVersion := "2.13.16"
ThisBuild / version      := IO.read(file("../VERSION")).trim
ThisBuild / organization := "e91c"

lazy val root = (project in file("."))
  .settings(
    name := "e91-cpu",
    libraryDependencies ++= Seq(
      // Chisel 6 起由 Chips Alliance 发布：groupId 为 org.chipsalliance
      "org.chipsalliance" %% "chisel"     % "6.7.0",
      "edu.berkeley.cs"   %% "chiseltest" % "6.0.0" % Test
    ),
    scalacOptions ++= Seq(
      "-deprecation",
      "-feature",
      "-Xcheckinit",
      "-language:reflectiveCalls"
    ),
    // 让测试能以项目根目录相对路径读取 golden 向量
    Test / fork := true,
    Test / javaOptions ++= Seq("-Xss512m", "-Xmx2g") ++
      sys.props.toSeq.collect { case (key, value) if key.startsWith("e91c.") => s"-D$key=$value" },
    addCompilerPlugin("org.chipsalliance" % "chisel-plugin" % "6.7.0" cross CrossVersion.full)
  )
