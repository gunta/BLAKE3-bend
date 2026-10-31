//! turboblake's --recursive (b3sum has no such flag), beside upstream's
//! cli_tests.rs.

use duct::cmd;
use std::fs;
use std::path::{Path, PathBuf};

fn exe() -> PathBuf {
    env!("CARGO_BIN_EXE_turboblake").into()
}

fn line(path: &str, data: &[u8]) -> String {
    format!("{}  {}\n", blake3::hash(data).to_hex(), path)
}

/// tree/a.txt, tree/b/c.txt, tree/b/d/e.txt, tree/b-x.txt, tree/empty/
fn tree(root: &Path) {
    let t = root.join("tree");
    fs::create_dir_all(t.join("b/d")).unwrap();
    fs::create_dir_all(t.join("empty")).unwrap();
    fs::write(t.join("a.txt"), b"a").unwrap();
    fs::write(t.join("b/c.txt"), b"c").unwrap();
    fs::write(t.join("b/d/e.txt"), b"e").unwrap();
    fs::write(t.join("b-x.txt"), b"x").unwrap();
}

#[test]
fn test_recursive_lists_regular_files_depth_first_in_name_order() {
    let dir = tempfile::tempdir().unwrap();
    tree(dir.path());
    // "b" sorts before "b-x.txt", so b's files come first (`find | sort`
    // would put b-x.txt first: '-' < '/')
    let expected = line("tree/a.txt", b"a")
        + &line("tree/b/c.txt", b"c")
        + &line("tree/b/d/e.txt", b"e")
        + &line("tree/b-x.txt", b"x");
    let output = cmd!(exe(), "--recursive", "tree").dir(dir.path()).stdout_capture().run().unwrap();
    assert_eq!(expected.as_bytes(), &output.stdout[..]);
    // a trailing slash adds none
    let output = cmd!(exe(), "--recursive", "tree/").dir(dir.path()).stdout_capture().run().unwrap();
    assert_eq!(expected.as_bytes(), &output.stdout[..]);
}

#[test]
#[cfg(unix)]
fn test_recursive_skips_links_and_special_files() {
    let dir = tempfile::tempdir().unwrap();
    tree(dir.path());
    let t = dir.path().join("tree");
    std::os::unix::fs::symlink("a.txt", t.join("link.txt")).unwrap();
    std::os::unix::fs::symlink("b", t.join("linkdir")).unwrap();
    cmd!("mkfifo", t.join("fifo")).run().unwrap();
    let expected = line("tree/a.txt", b"a")
        + &line("tree/b/c.txt", b"c")
        + &line("tree/b/d/e.txt", b"e")
        + &line("tree/b-x.txt", b"x");
    let output = cmd!(exe(), "--recursive", "tree").dir(dir.path()).stdout_capture().run().unwrap();
    assert_eq!(expected.as_bytes(), &output.stdout[..]);
    // a link given as an argument is followed
    let output = cmd!(exe(), "--recursive", "tree/linkdir").dir(dir.path()).stdout_capture().run().unwrap();
    let expected = line("tree/linkdir/c.txt", b"c") + &line("tree/linkdir/d/e.txt", b"e");
    assert_eq!(expected.as_bytes(), &output.stdout[..]);
}

#[test]
fn test_recursive_keeps_file_arguments_in_order() {
    let dir = tempfile::tempdir().unwrap();
    tree(dir.path());
    fs::write(dir.path().join("first"), b"1").unwrap();
    fs::write(dir.path().join("last"), b"2").unwrap();
    let output = cmd!(exe(), "--recursive", "first", "tree/b", "missing", "last")
        .dir(dir.path())
        .stdout_capture()
        .stderr_capture()
        .unchecked()
        .run()
        .unwrap();
    assert!(!output.status.success());
    let expected = line("first", b"1") + &line("tree/b/c.txt", b"c") + &line("tree/b/d/e.txt", b"e") + &line("last", b"2");
    assert_eq!(expected.as_bytes(), &output.stdout[..]);
    let missing = fs::File::open(dir.path().join("missing")).unwrap_err();
    assert_eq!(format!("turboblake: missing: {}\n", missing).as_bytes(), &output.stderr[..]);
}

#[test]
fn test_recursive_empty_directory() {
    let dir = tempfile::tempdir().unwrap();
    fs::create_dir(dir.path().join("empty")).unwrap();
    let output = cmd!(exe(), "--recursive", "empty").dir(dir.path()).stdout_capture().run().unwrap();
    assert!(output.stdout.is_empty());
}

#[test]
fn test_directory_without_recursive_is_still_an_error() {
    let dir = tempfile::tempdir().unwrap();
    tree(dir.path());
    let output = cmd!(exe(), "tree").dir(dir.path()).stdout_capture().stderr_capture().unchecked().run().unwrap();
    assert!(!output.status.success());
    assert!(output.stdout.is_empty());
    assert!(String::from_utf8_lossy(&output.stderr).starts_with("turboblake: tree: "));
}

#[test]
#[cfg(unix)]
fn test_recursive_reports_an_unreadable_directory_and_goes_on() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    tree(dir.path());
    let locked = dir.path().join("tree/b/d");
    fs::set_permissions(&locked, fs::Permissions::from_mode(0o000)).unwrap();
    let denied = fs::read_dir(&locked).err();
    let output = cmd!(exe(), "--recursive", "tree").dir(dir.path()).stdout_capture().stderr_capture().unchecked().run().unwrap();
    fs::set_permissions(&locked, fs::Permissions::from_mode(0o755)).unwrap();
    // root reads it anyway
    let Some(denied) = denied else { return };
    assert!(!output.status.success());
    let expected = line("tree/a.txt", b"a") + &line("tree/b/c.txt", b"c") + &line("tree/b-x.txt", b"x");
    assert_eq!(expected.as_bytes(), &output.stdout[..]);
    assert_eq!(format!("turboblake: tree/b/d: {}\n", denied).as_bytes(), &output.stderr[..]);
}

#[test]
fn test_recursive_many_files_and_check() {
    // more files than a batch (2048), so the engine takes them in two
    let dir = tempfile::tempdir().unwrap();
    let mut expected = Vec::new();
    for i in 0..2100usize {
        let rel = format!("many/{:02}/{:04}", i % 37, i);
        let data: Vec<u8> = (0..(i * 37) % 9000).map(|k| (k * 7 + i) as u8).collect();
        fs::create_dir_all(dir.path().join(&rel).parent().unwrap()).unwrap();
        fs::write(dir.path().join(&rel), &data).unwrap();
        expected.push((rel.clone(), line(&rel, &data)));
    }
    expected.sort();
    let expected: String = expected.into_iter().map(|(_, l)| l).collect();
    let output = cmd!(exe(), "--recursive", "many").dir(dir.path()).stdout_capture().run().unwrap();
    assert_eq!(expected, String::from_utf8(output.stdout).unwrap());

    fs::write(dir.path().join("sums"), &expected).unwrap();
    cmd!(exe(), "--check", "--quiet", "sums").dir(dir.path()).run().unwrap();
    fs::write(dir.path().join("many/05/0005"), b"changed").unwrap();
    let output = cmd!(exe(), "--check", "--quiet", "sums").dir(dir.path()).stdout_capture().unchecked().run().unwrap();
    assert!(!output.status.success());
    assert_eq!(&b"many/05/0005: FAILED\n"[..], &output.stdout[..]);
}

#[test]
fn test_recursive_with_other_flags() {
    let dir = tempfile::tempdir().unwrap();
    tree(dir.path());
    let output = cmd!(exe(), "--recursive", "--tag", "tree/b").dir(dir.path()).read().unwrap();
    let expected = format!(
        "BLAKE3 (tree/b/c.txt) = {}\nBLAKE3 (tree/b/d/e.txt) = {}",
        blake3::hash(b"c").to_hex(),
        blake3::hash(b"e").to_hex()
    );
    assert_eq!(expected, output);
    let key = [7u8; 32];
    let output = cmd!(exe(), "--recursive", "--keyed", "tree/b").dir(dir.path()).stdin_bytes(&key[..]).read().unwrap();
    let expected = format!(
        "{}  tree/b/c.txt\n{}  tree/b/d/e.txt",
        blake3::keyed_hash(&key, b"c").to_hex(),
        blake3::keyed_hash(&key, b"e").to_hex()
    );
    assert_eq!(expected, output);
}

#[test]
fn test_recursive_conflicts_with_check_and_raw() {
    let dir = tempfile::tempdir().unwrap();
    tree(dir.path());
    for flag in ["--check", "--raw"] {
        let output = cmd!(exe(), "--recursive", flag, "tree").dir(dir.path()).stderr_capture().unchecked().run().unwrap();
        assert!(!output.status.success(), "--recursive {flag}");
    }
}
