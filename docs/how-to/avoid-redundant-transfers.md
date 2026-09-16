# Avoid redundant transfers

Inbound SFTP folders have no recursive server-side checksum. To skip downloads,
set `NVFTP_DOWNLOAD_MANIFEST` to a producer-maintained file outside the incoming
folder. The producer must update it only after all incoming files are complete.
The target job checkpoints that manifest only after validation and MR handling
succeed.

Outbound runs on target default-branch pushes. `lftp mirror` compares the local
and remote trees and transfers the needed changes. A `.nvftp-sync-manifest`
containing the Git commit and tree hash is written after successful
publication.
