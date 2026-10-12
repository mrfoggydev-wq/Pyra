using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Reflection;

internal static class PyraLauncher
{
    private const string ApplicationName = "@@APP_NAME@@";
    private const string BundleId = "@@BUNDLE_ID@@";
    private const string SourceFilename = "@@SOURCE_FILENAME@@";
    private const bool SdkMode = @@SDK_MODE@@;

    private static string Quote(string value)
    {
        StringBuilder quoted = new StringBuilder("\"");
        int backslashes = 0;
        foreach (char character in value)
        {
            if (character == '\\')
            {
                backslashes++;
            }
            else if (character == '"')
            {
                quoted.Append('\\', backslashes * 2 + 1).Append(character);
                backslashes = 0;
            }
            else
            {
                quoted.Append('\\', backslashes).Append(character);
                backslashes = 0;
            }
        }
        quoted.Append('\\', backslashes * 2).Append('"');
        return quoted.ToString();
    }

    private static long GetUncompressedBundleSize()
    {
        using (Stream bundle = Assembly.GetExecutingAssembly().GetManifestResourceStream("PyraBundle"))
        using (ZipArchive archive = new ZipArchive(bundle, ZipArchiveMode.Read))
        {
            long totalSize = 0;
            foreach (ZipArchiveEntry entry in archive.Entries)
                totalSize += entry.Length;
            return totalSize;
        }
    }

    private static string SelectCacheRoot(long requiredBytes)
    {
        List<string> candidates = new List<string>();
        string configuredRoot = Environment.GetEnvironmentVariable("PYRA_CACHE_DIR");
        if (!String.IsNullOrWhiteSpace(configuredRoot))
            candidates.Add(configuredRoot);

        string executableDirectory = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        candidates.Add(Path.Combine(executableDirectory, ".pyra-cache"));
        string localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        candidates.Add(Path.Combine(localAppData, "Pyra"));
        candidates.Add(Path.Combine(Path.GetTempPath(), "Pyra"));

        foreach (string candidate in candidates)
        {
            try
            {
                string fullPath = Path.GetFullPath(candidate);
                Directory.CreateDirectory(fullPath);
                string driveRoot = Path.GetPathRoot(fullPath);
                DriveInfo drive = new DriveInfo(driveRoot);
                if (drive.IsReady && drive.AvailableFreeSpace >= requiredBytes + 64L * 1024 * 1024)
                    return fullPath;
            }
            catch (IOException)
            {
            }
            catch (UnauthorizedAccessException)
            {
            }
            catch (ArgumentException)
            {
            }
        }

        throw new IOException(
            "Недостаточно места для распаковки Pyra. Освободите место или задайте PYRA_CACHE_DIR на другом диске.");
    }

    private static int Main(string[] arguments)
    {
        try
        {
            string appData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string cacheRoot = SelectCacheRoot(GetUncompressedBundleSize());
            string extractionRoot = Path.Combine(cacheRoot, ApplicationName, BundleId);
            string appRoot = Path.Combine(extractionRoot, "app");
            string readyFile = Path.Combine(extractionRoot, ".ready");
            if (!File.Exists(readyFile))
            {
                Directory.CreateDirectory(extractionRoot);
                using (Stream bundle = Assembly.GetExecutingAssembly().GetManifestResourceStream("PyraBundle"))
                using (ZipArchive archive = new ZipArchive(bundle, ZipArchiveMode.Read))
                {
                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {
                        string destination = Path.GetFullPath(Path.Combine(extractionRoot, entry.FullName));
                        string root = Path.GetFullPath(extractionRoot) + Path.DirectorySeparatorChar;
                        if (!destination.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                            throw new InvalidDataException("Invalid path in application bundle.");
                        if (entry.FullName.EndsWith("/", StringComparison.Ordinal))
                        {
                            Directory.CreateDirectory(destination);
                            continue;
                        }
                        Directory.CreateDirectory(Path.GetDirectoryName(destination));
                        using (Stream input = entry.Open())
                        using (Stream output = File.Create(destination))
                            input.CopyTo(output);
                    }
                }
                File.WriteAllText(readyFile, BundleId);
            }

            string runtimeRoot = Path.Combine(extractionRoot, "runtime");
            string python = Path.Combine(runtimeRoot, "python.exe");
            string bootstrap = Path.Combine(appRoot, SdkMode ? "_pyra_cli.py" : "_pyra_bootstrap.py");
            string commandLine = Quote(bootstrap);
            if (!SdkMode)
                commandLine += " " + Quote(SourceFilename);
            foreach (string argument in arguments)
                commandLine += " " + Quote(argument);

            ProcessStartInfo startInfo = new ProcessStartInfo(python, commandLine);
            startInfo.UseShellExecute = false;
            startInfo.EnvironmentVariables["PYTHONHOME"] = runtimeRoot;
            startInfo.EnvironmentVariables["PYRA_EMBEDDED_RUNTIME"] = "1";
            string virtualEnvironment = Environment.GetEnvironmentVariable("VIRTUAL_ENV");
            string packageDirectory;
            if (!String.IsNullOrWhiteSpace(virtualEnvironment))
            {
                packageDirectory = Path.Combine(virtualEnvironment, "Lib", "site-packages");
            }
            else
            {
                string configuredPackages = Environment.GetEnvironmentVariable("PYRA_PACKAGE_DIR");
                string projectEnvironment = Path.Combine(Environment.CurrentDirectory, ".venv");
                if (!String.IsNullOrWhiteSpace(configuredPackages))
                    packageDirectory = configuredPackages;
                else if (File.Exists(Path.Combine(projectEnvironment, "Scripts", "python.exe")))
                    packageDirectory = Path.Combine(projectEnvironment, "Lib", "site-packages");
                else
                    packageDirectory = Path.Combine(appData, "Pyra", "packages");
            }
            startInfo.EnvironmentVariables["PYRA_PACKAGE_DIR"] = packageDirectory;
            startInfo.EnvironmentVariables["PYTHONPATH"] = packageDirectory;
            using (Process process = Process.Start(startInfo))
            {
                process.WaitForExit();
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            Console.Error.WriteLine("Pyra launch failed: " + error.Message);
            Console.Error.WriteLine("The bundled Python runtime could not be started.");
            return 1;
        }
    }
}