using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Threading.Tasks;
using System.Windows.Forms;

internal sealed class PyraInstallerForm : Form
{
    private readonly Label status = new Label();
    private readonly ProgressBar progress = new ProgressBar();
    private readonly Button installButton = new Button();

    internal PyraInstallerForm()
    {
        Text = "Установка Pyra";
        Width = 460;
        Height = 190;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;

        Label title = new Label();
        title.Text = "Установить Pyra для всех пользователей";
        title.SetBounds(20, 18, 410, 28);
        title.Font = new System.Drawing.Font(Font, System.Drawing.FontStyle.Bold);

        status.Text = "Pyra.exe встроен в этот установщик";
        status.SetBounds(20, 62, 410, 24);

        progress.SetBounds(20, 94, 410, 18);
        progress.Style = ProgressBarStyle.Marquee;
        progress.MarqueeAnimationSpeed = 0;

        installButton.Text = "Установить Pyra";
        installButton.SetBounds(275, 124, 155, 32);
        installButton.Anchor = AnchorStyles.Top | AnchorStyles.Right | AnchorStyles.Bottom;
        installButton.Click += InstallClicked;

        Controls.Add(title);
        Controls.Add(status);
        Controls.Add(progress);
        Controls.Add(installButton);
        AcceptButton = installButton;
    }

    private async void InstallClicked(object sender, EventArgs eventArgs)
    {
        if (!IsAdministrator())
        {
            MessageBox.Show(
                this,
                "Для установки в Program Files и изменения системного PATH запустите PyraInstaller.exe от имени администратора.",
                "Нужны права администратора",
                MessageBoxButtons.OK,
                MessageBoxIcon.Warning);
            return;
        }

        installButton.Enabled = false;
        progress.MarqueeAnimationSpeed = 24;
        status.Text = "Установка встроенного Pyra.exe...";

        try
        {
            await Task.Run(() => InstallEmbeddedPyra());
            status.Text = "Pyra установлена";
            MessageBox.Show(
                this,
                "Pyra установлена в:\n" + GetInstallDirectory() +
                "\n\nОткройте новый терминал и введите: pyra --version",
                "Готово",
                MessageBoxButtons.OK,
                MessageBoxIcon.Information);
        }
        catch (Exception error)
        {
            status.Text = "Установка не выполнена";
            MessageBox.Show(this, error.Message, "Ошибка установки", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            installButton.Enabled = true;
            progress.MarqueeAnimationSpeed = 0;
        }
    }

    private static void InstallEmbeddedPyra()
    {
        string installDirectory = GetInstallDirectory();
        string temporaryFile = Path.Combine(Path.GetTempPath(), "Pyra-" + Guid.NewGuid().ToString("N") + ".exe");
        string stagedFile = Path.Combine(installDirectory, "Pyra.exe.new");
        string installedFile = Path.Combine(installDirectory, "Pyra.exe");

        try
        {
            using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("PyraExecutable"))
            {
                if (resource == null)
                    throw new InvalidDataException("В установщике не найден встроенный Pyra.exe.");
                using (FileStream output = File.Create(temporaryFile))
                    resource.CopyTo(output);
            }

            if (!IsWindowsExecutable(temporaryFile))
                throw new InvalidDataException("Встроенный Pyra.exe повреждён или имеет неверный формат.");

            Directory.CreateDirectory(installDirectory);
            File.Copy(temporaryFile, stagedFile, true);
            if (File.Exists(installedFile))
                File.Replace(stagedFile, installedFile, null);
            else
                File.Move(stagedFile, installedFile);

            AddToSystemPath(installDirectory);
        }
        finally
        {
            if (File.Exists(temporaryFile))
                File.Delete(temporaryFile);
            if (File.Exists(stagedFile))
                File.Delete(stagedFile);
        }
    }

    private static string GetInstallDirectory()
    {
        return Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            "Pyra");
    }

    private static bool IsAdministrator()
    {
        using (WindowsIdentity identity = WindowsIdentity.GetCurrent())
        {
            WindowsPrincipal principal = new WindowsPrincipal(identity);
            return principal.IsInRole(WindowsBuiltInRole.Administrator);
        }
    }

    private static bool IsWindowsExecutable(string path)
    {
        using (FileStream file = File.OpenRead(path))
        {
            return file.Length > 1024 && file.ReadByte() == 'M' && file.ReadByte() == 'Z';
        }
    }

    private static void AddToSystemPath(string directory)
    {
        string currentPath = Environment.GetEnvironmentVariable("Path", EnvironmentVariableTarget.Machine) ?? "";
        string fullDirectory = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar);
        foreach (string pathEntry in currentPath.Split(';'))
        {
            string entry = pathEntry.Trim().Trim('"');
            if (String.IsNullOrWhiteSpace(entry))
                continue;
            string fullEntry = Path.GetFullPath(Environment.ExpandEnvironmentVariables(entry))
                .TrimEnd(Path.DirectorySeparatorChar);
            if (String.Equals(fullEntry, fullDirectory, StringComparison.OrdinalIgnoreCase))
            {
                BroadcastEnvironmentChange();
                return;
            }
        }

        string updatedPath = String.IsNullOrWhiteSpace(currentPath)
            ? fullDirectory
            : currentPath.TrimEnd(';') + ";" + fullDirectory;
        Environment.SetEnvironmentVariable("Path", updatedPath, EnvironmentVariableTarget.Machine);
        BroadcastEnvironmentChange();
    }

    private static void BroadcastEnvironmentChange()
    {
        IntPtr result;
        SendMessageTimeout(
            new IntPtr(0xffff),
            0x001A,
            IntPtr.Zero,
            "Environment",
            0x0002,
            5000,
            out result);
    }

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr SendMessageTimeout(
        IntPtr window,
        uint message,
        IntPtr wParam,
        string lParam,
        uint flags,
        uint timeout,
        out IntPtr result);
}

internal static class PyraInstallerProgram
{
    [STAThread]
    private static void Main()
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new PyraInstallerForm());
    }
}