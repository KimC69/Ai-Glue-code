# shell.nix — Environnement de build Android pour le Studio IA mobile APK.
# Fournit JDK 17 + un Android SDK minimal (build-tools, platform-tools, platform 34).
# Utilisation : nix-shell agents/mobile-apk/shell.nix

{ pkgs ? import <nixpkgs> { config.android_sdk.accept_license = true; } }:

let
  androidComposition = pkgs.androidenv.composeAndroidPackages {
    cmdLineToolsVersion = "13.0";
    platformToolsVersion = "35.0.1";
    buildToolsVersions = [ "34.0.0" ];
    platformVersions = [ "34" ];
    includeNDK = false;
    includeEmulator = false;
    includeSystemImages = false;
    includeSources = false;
  };
in
pkgs.mkShell {
  buildInputs = [ pkgs.jdk17 androidComposition.androidsdk ];

  shellHook = ''
    export JAVA_HOME="${pkgs.jdk17}/lib/openjdk"
    export ANDROID_SDK_ROOT="${androidComposition.androidsdk}/libexec/android-sdk"
    export ANDROID_HOME="$ANDROID_SDK_ROOT"
    export PATH="$ANDROID_SDK_ROOT/build-tools/34.0.0:$ANDROID_SDK_ROOT/platform-tools:$PATH"
    echo "Studio IA — environnement Android prêt"
    echo "JAVA_HOME=$JAVA_HOME"
    echo "ANDROID_SDK_ROOT=$ANDROID_SDK_ROOT"
  '';
}
