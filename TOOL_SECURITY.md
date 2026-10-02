# Tool security

Tools declare a permission class and argument schema. The registry validates tool names,
unknown/missing arguments, argument types and the run's allowed permission set before
dispatch. Permission classes are read, workspace-write, shell, git mutation, external API
and destructive. The default coding run has no external-API or destructive tool.

All file-oriented tools call the same canonical workspace validator. It rejects absolute
paths, Windows drive paths, `..`, NULs and existing symlinks that resolve outside the
workspace. Shell commands execute only inside the isolated workspace and block credential
enumeration, host-style absolute system paths, traversal and network transfer utilities.
Container isolation remains the primary shell boundary.

Prompts delimit issue/repository content as untrusted data. Repository instructions and
tool output cannot alter platform policy or grant permissions. The UI persists and shows
operations, safe arguments, observations and validation evidence; private model reasoning
is neither persisted nor streamed.

Patch publication separately rejects malformed/empty diffs, credential files, private
keys and common embedded credential patterns. The model cannot call PR creation.
